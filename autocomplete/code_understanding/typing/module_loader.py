'''This module handles 'loading'/importing modules found in analyzing source.

We're of course not actually loading the module in the traditional sense.
Instead, we're doing one of a few things:

1) Generating a Module instance from an actual source file including a full
CFG.
2) Generating a Module instance from an interface stub file (which we may have
created) and returning types.
3) If we can't find a module that's imported, we will create an 'Unknown'
module.

Python's tutorial on module's is a rather quick, helpful reference for some
peculiarities like the purposes of __all__:
https://docs.python.org/3/tutorial/modules.html
'''
import attr
import importlib
import os
import sys
from typing import Dict, Set, Tuple
from enum import Enum

import typeshed
from . import (api, frame, serialization)
from .collector import FileContext
from .errors import (InvalidModuleError, UnableToReadModuleFileError)
from .language_objects import (LazyModule, Module, ModuleImpl, ModuleType, NativeModule, create_main_module)
from .pobjects import (AugmentedObject, NativeObject, PObject, UnknownObject)
from ...nsn_logging import (debug, info, warning)

NATIVE_MODULE_WHITELIST = set(['six', 're'])

# This is primarily to ensure we never read in a file twice - which should be essentially impossible
# given the public API.
__loaded_paths: Set[str] = set()

keep_graphs_default = False


class ModuleSourceType(Enum):
  BUILTIN = 0
  COMPILED = 1
  BAD = 2
  NORMAL = 3

  def should_be_natively_loaded(self):
    return self != ModuleSourceType.NORMAL


@attr.s(hash=False, cmp=False)
class ModuleKey:
  '''A key for uniquely identifying and retrieving any module - builtin, compiled, or normal.'''
  module_source_type = attr.ib()
  # A unique identifier for the module. For builtins, this can just be the name of the module. For
  # modules with associated filenames, this will be the filepath to the module.
  id = attr.ib()
  _hash = attr.ib(None, init=False)
  # This only applies to non-builtins and is the path from which this module should be loaded.
  # _loader_path = attr.ib(None, init=False) #

  @staticmethod
  def from_filename(filename):
    ext = os.path.splitext(filename)[1]
    if ext == '.so':
      type_ = ModuleSourceType.COMPILED
    elif ext == '.py' or '.pyi':
      type_ = ModuleSourceType.NORMAL
    else:
      return ModuleKey(ModuleSourceType.BAD, os.path.abspath(filename))
    return ModuleKey(type_, os.path.abspath(filename))

  def get_module_basename(self):
    if not self.is_loadable_by_file():
      return self.id
    return module_name_from_filename(self.get_filename(), basename_only=True)

  def get_filename(self, prefer_stub=True):
    assert self.is_loadable_by_file()
    # Can't cache because 2 versions - stub and not stub.
    return loader_path_from_file_module_id(self.id, prefer_stub=prefer_stub)

  def is_loadable_by_file(self):
    return self.module_source_type == ModuleSourceType.NORMAL or self.module_source_type == ModuleSourceType.COMPILED

  def is_bad(self):
    return self.module_source_type == ModuleSourceType.BAD

  def serialize(self):
    return self.module_source_type.value, self.id

  @staticmethod
  def deserialize(args):
    return ModuleKey(ModuleSourceType(args[0]), args[1])

  def __hash__(self):
    if not self._hash:
      self._hash = hash((self.module_source_type, self.id))
    return self._hash

  def __eq__(self, other):
    return hash(self) == hash(other)


def module_id_from_filename(filename):
  # TODO: Generalize more. E.g.:
  # third_party:<pypi_id>/<path_relative_to_module>
  # local:abs_path_to_module
  # sys:<path_from_sys>
  # Perhaps making tuples w/ ModuleType instead of strings..
  # Maybe deal with versioning?
  # How to handle messiness w/multiple versions across sys.path?
  return filename


def loader_path_from_file_module_id(module_id, prefer_stub):
  assert os.path.exists(module_id)
  if not prefer_stub:
    return module_id

  if f'lib{os.sep}python' in module_id:
    # Likely third-party or sys-module. Try to find a typeshed match.
    for path in sorted(filter(lambda f: f'lib{os.sep}python' in f, sys.path), key=lambda p: -len(p)):
      assert not path[0] == '.'
      # TODO: Broader relative path support.
      if path == module_id[:len(path)]:
        rel_path = os.path.relpath(module_id, path)
        module_name = module_name_from_filename(rel_path)
        try:
          return _stub_filename_from_module_name(module_name)
        except ValueError:
          return module_id
  return module_id


def module_name_from_filename(filename, basename_only=False):
  basename = os.path.basename(filename)
  if basename == '__init__.py' or basename == '__init__.pyi':
    return os.path.basename(os.path.dirname(filename))
  # Note: we manually remove the extension here rather than using os.splitext. This is to remove
  # all '.' parts from the name - which aren't allowable within the context of an individual
  # module name.
  # This mostly matters for native modules - e.g.:
  # '/usr/lib/python3.7/lib-dynload/_hashlib.cpython-37m-x86_64-linux-gnu.so'
  # The name we want is _hashlib - not _hashlib.cpython-37m-x86_64-linux-gnu.
  module_basename = basename[:basename.index('.')]
  assert module_basename
  if basename_only:
    return module_basename

  dirname = os.path.dirname(filename)
  if not dirname:
    return module_basename
  return f'{dirname.replace(os.sep, ".")}.{module_basename}'


def join_module_attribute(module_name, attribute_name):
  if module_name[-1] == '.':
    return f'{module_name}{attribute_name}'
  return f'{module_name}.{attribute_name}'


def get_pobject_from_module(module_name: str, pobject_name: str, directory: str) -> PObject:
  # See if there's a module we can read that'd correspond to the full name.
  # module_name will only end with '.' if it's purely periods- 1 or more. In that
  # case, we don't want to mess things up by adding an additional period at the
  # end of the module name.
  full_pobject_name = join_module_attribute(module_name, pobject_name)
  module_key = get_module_info_from_name(full_pobject_name, directory)[0]
  if not module_key.is_bad():
    try:
      return AugmentedObject(get_module_from_key(module_key, unknown_fallback=False), imported=True)
    except InvalidModuleError:
      pass
  module_key = get_module_info_from_name(module_name, directory)[0]
  module = get_module_from_key(module_key)
  # Try to get pobject_name as a member of module if module is a package.
  # If the module is already loading, then we don't want to check if pobject_name is in module
  # because it will cause headaches. So try getting full_object_name as a package instead.
  if (not isinstance(module, LazyModule) or not module._loading) and pobject_name in module:
    return AugmentedObject(module[pobject_name], imported=True)

  return UnknownObject(full_pobject_name, imported=True)

__module_key_module_dict: Dict[Tuple[ModuleKey, str], Module] = {}

def module_key_index(module_key, force_real):
  return (module_key, module_key.get_filename(prefer_stub=not force_real) if module_key.is_loadable_by_file() else None)

def get_module_from_key(module_key, unknown_fallback=True, lazy=True, include_graph=False, force_real=False):
  module_key, is_package, module_type = get_module_info_from_module_key(module_key)
  global __module_key_module_dict
  if module_key_index(module_key, force_real) in __module_key_module_dict:
    module = __module_key_module_dict[module_key_index(module_key, force_real)]
    if isinstance(module, LazyModule):
      if include_graph:
        if not module.graph and module.has_loaded_or_loading():
          # Damn, alreadly loaded but did not keep the graph the first time...
          with open(module.filename) as f:
            module.graph = api.graph_from_source(''.join(f.readlines()), os.path.dirname(module.filename))
        else:
          module.keep_graph = True
      if not lazy and module.lazy and not module.has_loaded_or_loading():
        module.load()
        # Even if the module is loaded, it'll still act lazily unless we explicitly indicate not to.
        module.lazy = False
    elif include_graph and not module.graph:
      if not module_key.module_source_type.should_be_natively_loaded():
        # Damn, alreadly loaded but did not keep the graph the first time...
        with open(module_key.get_filename()) as f:
          module.graph = api.graph_from_source(''.join(f.readlines()), os.path.dirname(module.filename))
      else:
        warning(f'Cannot include graph on module that is natively loaded.')
    return module

  # We set this to None to start as a form of dependency-cycle-checking. This is the only way that
  # an object is this dict is None and we check if a value retrieved from it is None above.
  __module_key_module_dict[module_key_index(module_key, force_real)] = None
  try:
    module = _load_module_from_module_info(module_key,
                                           is_package,
                                           module_type,
                                           unknown_fallback=unknown_fallback,
                                           lazy=lazy,
                                           include_graph=include_graph,
                                           force_real=force_real)
  except InvalidModuleError:
    del __module_key_module_dict[module_key_index(module_key, force_real)]
    raise
  assert module is not None
  debug(f'Adding {module_key} to module dict.')
  __module_key_module_dict[module_key_index(module_key, force_real)] = module
  # # Note: This will essentially stop us from storing modules which are unreadable because they are
  # # sourced from invalid files. That's fine.
  # if filename is not None and os.path.exists(filename):
  #   __filename_module_dict[filename] = module
  return module


def load_module_from_source(source, filename, include_graph=False):
  module = create_main_module(sys.modules[__name__])
  if include_graph:
    module._members, graph = _module_exports_from_source(module, source, filename=filename, return_graph=True)
    module.graph = graph
  else:
    module._members = _module_exports_from_source(module, source, filename=filename)
  return module


def _load_module_exports_from_filename(module, filename, return_graph=False):
  try:
    with open(filename) as f:
      source = ''.join(f.readlines())
    info(f'Loading {filename}')
    # We allow typeshed files to be loaded twice as a peculiar special case.
    # A real module may be loaded using a typeshed stub, and subsequently the typeshed stub may be
    # loaded as itself with it's own different ModuleKey - these two thing are different
    # abstractions that happens to have the same underlying filename and thus are allowable to be
    # loaded twice. Alternatively, we could try to make these use the same ModuleKey, but it seems
    # that would get misleading - if something explicitly wants the typeshed version, it should
    # get the typeshed version.
    assert filename not in __loaded_paths or 'typeshed' in filename
    __loaded_paths.add(filename)
    return _module_exports_from_source(module, source, filename, return_graph=return_graph)
  except UnicodeDecodeError as e:
    warning(f'{filename}: {e}')
    raise UnableToReadModuleFileError(e)


def _load_module_from_module_info(module_key,
                                  is_package,
                                  module_type,
                                  unknown_fallback=True,
                                  lazy=True,
                                  include_graph=False, force_real=False) -> Module:
  if module_type == ModuleType.UNKNOWN_OR_UNREADABLE:
    if unknown_fallback:
      return _create_empty_module(module_key.id, module_type)
    else:
      raise InvalidModuleError(module_key.id)

  name = module_key.get_module_basename()
  if module_key.module_source_type.should_be_natively_loaded() or name in NATIVE_MODULE_WHITELIST:
    try:
      package = None
      if module_key.module_source_type == ModuleSourceType.COMPILED:
        package = package_from_directory(os.path.dirname(module_key.get_filename()))
      else:
        assert name[0] != '.'
      python_module = importlib.import_module(name, package)
    except ImportError:
      warning(f'Failed to natively import {name} {package}')
      return _create_empty_module(name, ModuleType.UNKNOWN_OR_UNREADABLE)
    else:
      return NativeModule(name,
                          module_type,
                          filename=module_key.id,
                          native_module=NativeObject(python_module, read_only=True))
  return _load_normal_module(module_key,
                             is_package=is_package,
                             module_type=module_type,
                             unknown_fallback=unknown_fallback,
                             lazy=lazy,
                             include_graph=include_graph,
                             force_real=force_real)


def _load_normal_module(module_key,
                        *,
                        is_package,
                        module_type=ModuleType.SYSTEM,
                        unknown_fallback=False,
                        lazy=True,
                        include_graph=False,
                        force_real=False) -> Module:
  assert module_key.module_source_type == ModuleSourceType.NORMAL
  name = module_key.get_module_basename()
  filename = module_key.get_filename(prefer_stub=not force_real)
  if not os.path.exists(filename):
    if not unknown_fallback:
      raise InvalidModuleError(filename)
    return _create_empty_module(name, ModuleType.UNKNOWN_OR_UNREADABLE)
  if lazy:
    return _create_lazy_module(name,
                               filename,
                               is_package=is_package,
                               module_type=module_type,
                               include_graph=include_graph)

  module = ModuleImpl(name=name,
                      module_type=module_type,
                      filename=filename,
                      members={},
                      is_package=is_package,
                      module_loader=sys.modules[__name__])

  try:
    if include_graph or keep_graphs_default:
      module._members, module.graph = _load_module_exports_from_filename(module, filename, include_graph
                                                                         or keep_graphs_default)
    else:
      module._members = _load_module_exports_from_filename(module, filename)
  except UnableToReadModuleFileError:
    if not unknown_fallback:
      raise InvalidModuleError(filename)
    return _create_empty_module(name, ModuleType.UNKNOWN_OR_UNREADABLE)
  return module


def _create_lazy_module(name, filename, is_package, module_type, include_graph) -> LazyModule:
  return LazyModule(name=name,
                    module_type=module_type,
                    filename=filename,
                    load_module_exports_from_filename=_load_module_exports_from_filename,
                    is_package=is_package,
                    keep_graph=include_graph or keep_graphs_default,
                    module_loader=sys.modules[__name__])


def _create_empty_module(name, module_type):
  return ModuleImpl(
      name=name,
      module_type=module_type,
      filename=name,  # TODO
      members={},
      is_package=False,
      module_loader=sys.modules[__name__])


def _module_exports_from_source(module, source, filename, return_graph=False) -> Dict[str, PObject]:
  with FileContext(filename):
    debug(f'len(__loaded_paths): {len(__loaded_paths)}')
    a_frame = frame.Frame(module=module, namespace=module, locals=module._members)
    graph = api.graph_from_source(source, filename, module)
    graph.process(a_frame)
  # Normally, exports wouldn't unclude protected members - but, internal members may rely on them
  # when running, so we through them in anyway for the heck of it.
  if return_graph:
    return a_frame._locals, graph
  return a_frame._locals


def get_module_info_from_module_key(module_key):
  if module_key.is_bad():
    return module_key, False, ModuleType.UNKNOWN_OR_UNREADABLE
  if module_key.module_source_type == ModuleSourceType.BUILTIN:
    module_type = ModuleType.BUILTIN
    is_package = False
  elif module_key.module_source_type == ModuleSourceType.COMPILED:
    module_type = ModuleType.COMPILED
    is_package = False
  else:
    module_type = module_type_from_filename(module_key.get_filename())
    is_package = _is_init(module_key.get_filename())
  return module_key, is_package, module_type


def get_module_info_from_name(name: str, curr_dir=None) -> Tuple[ModuleKey, bool, ModuleType]:
  is_package = False
  if name[0] == '.':
    assert os.path.exists(curr_dir), "Cannot get relative path w/o knowing current dir."
    relative_path = _relative_path_from_relative_module(name)
    absolute_path = os.path.abspath(os.path.join(curr_dir, relative_path))
    if os.path.exists(absolute_path):
      assert os.path.isdir(absolute_path)
      is_package = True
      for name in ('__init__.pyi', '__init__.py'):
        filename = os.path.join(absolute_path, name)
        if os.path.exists(filename):
          return ModuleKey.from_filename(filename), is_package, module_type_from_filename(filename)
    # Name refer's to a .py[i] module; not a package.
    for file_extension in ('.py', '.pyi'):
      filename = f'{absolute_path}{file_extension}'
      if os.path.exists(filename):
        return ModuleKey.from_filename(filename), False, module_type_from_filename(filename)
  package = None
  if name[0] == '.':
    package = package_from_directory(curr_dir)
  try:
    spec = importlib.util.find_spec(name, package)
  except (ImportError, AttributeError, ValueError) as e:
    # AttributeError: module '_warnings' has no attribute '__path__
    # find_spec can break for sys modules unexpectedly.
    debug(f'Exception while getting spec for {name}')
    debug(e)
  else:
    if spec:
      if spec.has_location:
        filename = spec.loader.get_filename()
        return get_module_info_from_filename(filename)
      return ModuleKey(ModuleSourceType.BUILTIN, name), False, ModuleType.BUILTIN
  debug(f'Could not find Module {name} - falling back to Unknown.')
  return ModuleKey(ModuleSourceType.BAD, name), False, ModuleType.UNKNOWN_OR_UNREADABLE


def _stub_filename_from_module_name(name) -> str:
  '''Retrieves the stub version of a module, if it exists.
  
  This currently only relies on typeshed, but in the future should also pull from some local repo.'''
  # TODO: local install + TYPESHED_HOME env variable like pytype:
  # https://github.com/google/pytype/blob/309a87fab8a861241823592157208e65c970f7b6/pytype/pytd/typeshed.py#L24
  typeshed_dir = os.path.dirname(typeshed.__file__)
  if name == '.' or name[0] == '.':
    raise ValueError()
  module_path_base = name.replace('.', os.sep)
  for top_level in ('stdlib', 'third_party'):
    # Sorting half to start with the lowest python level, half for consistency across runs.
    # Skip the version-2-only python files.
    for version in filter(lambda x: x != '2', sorted(os.listdir(os.path.join(typeshed_dir, top_level)))):
      for module_path in (os.path.join(module_path_base, "__init__.pyi"), f'{module_path_base}.pyi'):
        abs_module_path = os.path.join(typeshed_dir, top_level, version, module_path)
        if os.path.exists(abs_module_path):
          return abs_module_path
  raise ValueError(f'Did not find typeshed for {name}')


def get_module_info_from_filename(filename):
  ext = os.path.splitext(filename)[1]
  if ext != '.pyi' and ext != '.py':
    debug(f'Cannot read module filetype - {filename}')
    if ext == '.so':
      return ModuleKey.from_filename(filename), False, ModuleType.COMPILED
    return ModuleKey.from_filename(filename), False, ModuleType.UNKNOWN_OR_UNREADABLE
  return ModuleKey.from_filename(filename), _is_init(filename), module_type_from_filename(filename)


def module_type_from_filename(filename) -> ModuleType:
  # TODO: Refine / include LOCAL.
  # https://github.com/GabeDottl/autocomplete/issues/1
  for third_party in ('dist-packages', 'site-packages'):
    if third_party in filename:
      return ModuleType.PUBLIC
  return ModuleType.SYSTEM


def _relative_path_from_relative_module(name):
  if name == '.':
    return '.'

  dot_prefix_count = 0
  for char in name:
    if char != '.':
      break
    dot_prefix_count += 1

  remaining_name = name[dot_prefix_count:]
  if dot_prefix_count == 1:
    relative_prefix = f'.{os.sep}'
  else:
    relative_prefix = ''
    # TODO:
    # relative_prefix = f'..{os.sep}'* (dot_prefix_count - 1)
    for _ in range(dot_prefix_count - 1):
      relative_prefix += f'..{os.sep}'
  return f'{relative_prefix}{remaining_name.replace(".", os.sep)}'


def _is_init(filename):
  name = os.path.basename(filename)
  return '__init__.py' in name  # Implicitly includes __init__.pyi.


def package_from_directory(directory):
  for path in sorted(sys.path, key=lambda p: -len(p)):
    if path == directory[:len(path)]:
      relative = directory[len(path) + 1:]
      return relative.replace(os.sep, '.')
  assert False


def deserialize_hook_fn(type_str, obj):
  if type_str == NativeModule.__qualname__:
    return True, get_module_from_key(obj, '')
  if type_str == 'import_module':
    name, filename = obj
    return get_module_from_key(ModuleKey.from_filename(filename), is_package=_is_init(filename))
    #module_type=module_type_from_filename(filename))
  if type_str == 'from_import':
    filename = obj
    index = filename.rindex('.')
    module_name = filename[:index]
    object_name = filename[index + 1:]
    return get_pobject_from_module(module_name, object_name, os.path.dirname(filename))
  return False, None


def deserialize(type_str, obj):
  return serialization.deserialize(type_str, obj, hook_fn=deserialize_hook_fn)