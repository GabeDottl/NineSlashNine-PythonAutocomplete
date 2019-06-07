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
import importlib.util
import os
import sys
from typing import Dict, Set, Tuple
from enum import Enum
from functools import wraps

import typeshed
from . import (api, frame, serialization)
from .collector import FileContext
from .errors import (InvalidModuleError, UnableToReadModuleFileError)
from .language_objects import (LazyModule, Module, ModuleImpl, NativeModule, create_main_module)
from .pobjects import (AugmentedObject, NativeObject, PObject, UnknownObject)
from .utils import instance_memoize
from ...nsn_logging import (debug, info, warning)

NATIVE_MODULE_WHITELIST = set(['six', 're'])

# This is primarily to ensure we never read in a file twice - which should be essentially impossible
# given the public API.
__loaded_paths: Set[str] = set()
__module_key_module_dict: Dict[Tuple['ModuleKey', str], Module] = {}
__module_key_to_python_module = {}
# __module_key_graph_dict = {}  # TODO.

keep_graphs_default = False


class ModuleSourceType(Enum):
  BUILTIN = 0
  COMPILED = 1
  BAD = 2
  NORMAL = 3

  def should_be_natively_loaded(self):
    return self != ModuleSourceType.NORMAL


@attr.s(hash=False, cmp=False, str=False, repr=False)
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

  @instance_memoize
  def get_basename(self):
    if not self.is_loadable_by_file():
      return self.id
    return module_name_from_filename(self.get_filename(False), basename_only=True)

  def get_filename(self, prefer_stub):
    assert self.is_loadable_by_file()
    # Can't cache because 2 versions - stub and not stub.
    return loader_path_from_file_module_id(self.id, prefer_stub=prefer_stub)

  def is_package(self):
    return os.path.basename(self.get_filename(False)) == '__init__.py'

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

  def __str__(self):
    return f'ModuleKey({self.module_source_type}, {self.id})'

  def __repr__(self):
    return str(self)


def loader_path_from_file_module_id(module_id, prefer_stub):
  # assert os.path.exists(module_id)
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
  module_key = module_key_from_relative_module_name(full_pobject_name, directory)
  if not module_key.is_bad():
    try:
      return AugmentedObject(get_module_from_key(module_key, unknown_fallback=False), imported=True)
    except InvalidModuleError:
      pass
  module_key = module_key_from_relative_module_name(module_name, directory)
  module = get_module_from_key(module_key)
  # Try to get pobject_name as a member of module if module is a package.
  # If the module is already loading, then we don't want to check if pobject_name is in module
  # because it will cause headaches. So try getting full_object_name as a package instead.
  if (not isinstance(module, LazyModule) or not module._loading) and pobject_name in module:
    return AugmentedObject(module[pobject_name], imported=True)

  return UnknownObject(full_pobject_name, imported=True)


def remove_module_by_key(module_key):
  keys = [module_key_index(module_key, False), module_key_index(module_key, True)]
  for key in keys:
    if key in __module_key_module_dict:
      del __module_key_module_dict[key]

  filenames = [module_key.get_filename(False), module_key.get_filename(True)]
  for filename in filenames:
    if filename in __loaded_paths:
      __loaded_paths.remove(filename)


def module_key_index(module_key, force_real):
  return (module_key,
          module_key.get_filename(prefer_stub=not force_real) if module_key.is_loadable_by_file() else None)


def get_module_from_key(module_key, unknown_fallback=True, lazy=True, include_graph=False, force_real=False):
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
        with open(module_key.get_filename(False)) as f:
          module.graph = api.graph_from_source(''.join(f.readlines()), os.path.dirname(module.filename))
      else:
        warning(f'Cannot include graph on module that is natively loaded.')
    assert module
    return module

  module_key_index_value = module_key_index(module_key, force_real)
  try:
    # Note: We fill insert the module before loading incase there is a circular dependency in the
    # loading process. Oddly, this is valid.
    # TODO: Weakref.
    debug(f'Adding {module_key} to module dict.')
    module = __module_key_module_dict[module_key_index_value] = _create_module(
        module_key,
        unknown_fallback=unknown_fallback,
        lazy=lazy,
        include_graph=include_graph,
        force_real=force_real)
    if not lazy and module_key.is_loadable_by_file():
      filename = module_key.get_filename(prefer_stub=not force_real)
      try:
        if include_graph or keep_graphs_default:
          module._members, module.graph = _load_module_exports_from_filename(
              module, filename, include_graph or keep_graphs_default)
        else:
          module._members = _load_module_exports_from_filename(module, filename)
      except UnableToReadModuleFileError:
        if not unknown_fallback:
          raise InvalidModuleError(filename)
  except InvalidModuleError:
    if module_key_index_value in __module_key_module_dict:
      del __module_key_module_dict[module_key_index_value]
    raise
  assert module is not None
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


def _create_module(module_key, unknown_fallback=True, lazy=True, include_graph=False,
                   force_real=False) -> Module:
  '''Creates the module from the provided specification, but will not load anything if it is normal.'''
  if module_key.is_bad() or (module_key.is_loadable_by_file()
                             and not os.path.exists(module_key.get_filename(prefer_stub=False))):
    if unknown_fallback:
      return _create_empty_module(module_key.id)
    else:
      raise InvalidModuleError(module_key.id)

  name = module_key.get_basename()
  if module_key.module_source_type.should_be_natively_loaded() or name in NATIVE_MODULE_WHITELIST:
    try:
      python_module = get_python_module_from_module_key(module_key)
    except ImportError:
      if unknown_fallback:
        return _create_empty_module(module_key.id)
      else:
        raise InvalidModuleError(module_key.id)
    else:
      return NativeModule(name,
                          filename=module_key.id,
                          native_module=NativeObject(python_module, read_only=True))
  return _load_normal_module(module_key,
                             is_package=module_key.is_package(),
                             unknown_fallback=unknown_fallback,
                             lazy=lazy,
                             include_graph=include_graph,
                             force_real=force_real)


def _fullname_and_package_path_from_filename(filename):
  '''Extrapolates the full-path for a given module filename by recursing up the file-tree.'''
  fullname = os.path.splitext(os.path.basename(filename))[0]
  if fullname == '__init__':
    fullname = ''
  package = os.path.dirname(filename)
  while True:
    if os.path.exists(os.path.join(package, '__init__.py')):
      fullname = f'{os.path.basename(package)}.{fullname}'
      package = os.path.dirname(package)
    else:
      break
  if fullname[-1] == '.':
    # Special case for packages.
    fullname = fullname[:-1]
  return fullname, package


def _package_spec_from_module_spec(module_spec):
  if _is_init(module_spec.origin):
    return module_spec
  else:
    directory = os.path.dirname(module_spec.origin)
    return importlib.util.spec_from_file_location(module_spec.parent, os.path.join(directory, '__init__.py'))


@wraps(__import__)
def _import_override(name, globals=None, locals=None, fromlist=(), level=0):
  '''Custom version of __import__.
  
  See this for comments on params:
  https://docs.python.org/3/library/functions.html#__import__'''
  # info(f'name: {name}')
  # Pull from sys.modules if possible.
  if name in sys.modules and not level:
    module = sys.modules[name]
  elif not name or level:
    # level is relative to this spec.
    spec = globals['__spec__']
    assert spec.has_location
    path_parts = spec.origin.split(os.sep)
    parent_package_directory = os.sep.join(path_parts[:-level])
    if level > 1:
      spec_name_parts = spec.parent.split('.')
      package_name = '.'.join(spec_name_parts[:1 - level])
    else:
      package_name = spec.parent
    module_filename = filename_from_relative_module_name(f'.{name}', parent_package_directory)
    assert module_filename
    if _is_init(module_filename):
      relative_path = os.path.split(module_filename)[0][len(parent_package_directory) + 1:]
    else:
      relative_path = module_name_from_filename(module_filename[len(parent_package_directory) + 1:])
    if relative_path:
      name = f'{package_name}.{relative_path.replace(os.sep, ".")}'
    else:
      name = package_name
    if _is_init(module_filename):
      # if name:
      #   name = f'{package_name}.{name}'
      # else:
      #   name = package_name
      # This is a bit of weird recursion magic... the else here will insert into sys.modules, so if
      # this gets recurred-into, the first branch will definitely pass - if it doesn't the first
      # time.
      if name in sys.modules:
        module = sys.modules[name]
      else:
        new_spec = importlib.util.spec_from_file_location(name, module_filename)
        module = _import_source_module(new_spec)

      if fromlist:
        package_directory = os.path.dirname(module_filename)
        # Possibly importing submodules - handle them.
        for from_name in fromlist:
          _import_from(module, package_directory, from_name)
        # return module
      elif '.' in package_name:
        assert False, "Need to return parent."
    else:  # submodule.
      new_spec = importlib.util.spec_from_file_location(name, module_filename)
      module = _import_source_module(new_spec)
  else:  # Use the regular import-system for non-relative imports.
    spec = importlib.util.find_spec(name, None)
    if not spec:
      raise ImportError(name)
    module = _import_source_module(spec)

  # Can't do anything if the module doesn't have a spec.
  if fromlist and hasattr(module, '__spec__'):
    for from_name in fromlist:
      if hasattr(module, from_name):
        continue
      _import_from(module, None, from_name)
  if '.' in name:
    # From: https://docs.python.org/3/library/functions.html#__import__
    # "When the name variable is of the form package.module, normally, the top-level package (the
    # name up till the first dot) is returned, not the module named by name. However, when a
    # non-empty fromlist argument is given, the module named by name is returned."
    if fromlist:
      return module
    else:
      package_name = name[:name.find('.')]
      out = sys.modules[package_name]
      # assert hasattr(out, module_name)
      return out

  return module


def _import_from(module, module_directory, from_name):
  # info(f'from_name: {from_name}')
  if hasattr(module, from_name):
    return
  module_spec = module.__spec__
  if not module_spec:
    raise ImportError(f'Unable to import {from_name} from {module.__name__}')
  if not module_directory and module_spec.has_location:
    module_directory = os.path.dirname(module_spec.origin)

  basenames_and_child_specs = []
  if module_directory:
    if not _is_init(module_spec.origin):
      # Do nothing for normal non-package modules.
      return
    if from_name == '*':
      def is_py_or_so(filename):
        ext = os.path.splitext(filename)[1]
        return ext == '.so' or ext == '.py'

      if hasattr(module, '__all__'):
        child_filenames = list(
            filter(lambda x: x,
                   [filename_from_relative_module_name(name, module_directory) for name in module.__all__]))
      else:
        child_filenames = [
            os.path.join(module_directory, f) for f in filter(is_py_or_so, os.listdir(module_directory))
        ]
    else:  # single from_name
      child_filenames = [filename_from_relative_module_name(f'.{from_name}', module_directory)]
      assert child_filenames[0]

    for child_filename in child_filenames:
      basename = module_name_from_filename(child_filename, basename_only=True)
      child_name = f'{module_spec.name}.{basename}'
      basenames_and_child_specs.append((basename, importlib.util.spec_from_file_location(child_name, child_filename)))
  else:  # no module_directory
    assert not from_name == '*'
    basenames_and_child_specs = [(from_name, importlib.util.find_spec(from_name, module_spec.name))]
  for basename, child_spec in basenames_and_child_specs:
    if not child_spec:
      if hasattr(module, basename):
        continue
      raise ImportError(f'{basename} is an invalid import from {module_spec.name}')
    child_module = _import_source_module(child_spec)
    # if '.' in basename:
    # basename = child_name[child_name.rfind('.') + 1:]
    setattr(module, basename, child_module)


def _import_source_module(spec):
  if spec.name in sys.modules:
    curr_module = sys.modules[spec.name]
    if curr_module.__spec__.origin != spec.origin:
      warning(f'Replacing module with name {spec.name} from {curr_module.__spec__.origin} to {spec.origin}')
    else:
      return curr_module
  # fake_builtins = importlib.util.module_from_spec(builtins.__spec__)
  # for k, v in python_module.__builtins__.items():
  #   setattr(fake_builtins, k, v)
  # setattr(fake_builtins, '__import__', _import_override)
  name = spec.name
  python_module = importlib.util.module_from_spec(spec)
  if '.' in name:
    if spec.parent == spec.name:
      filename = spec.origin
      if not filename:
        package_spec = None
      else:
        parent_directory = os.path.dirname(os.path.dirname(filename))
        parent_init = os.path.join(parent_directory, '__init__.py')
        package_spec = importlib.util.spec_from_file_location(name[:name.rfind('.')], parent_init)
    else:
      package_spec = _package_spec_from_module_spec(spec)
    if package_spec:
      assert _fullname_and_package_path_from_filename(package_spec.origin)[0] == package_spec.name, "mismatch"
      package_module = _import_source_module(package_spec)
      if package_module:
        base_name = name[name.rfind('.') + 1:]
        # info(f'(package_module.__name__, base_name): {(package_module.__name__, base_name)}')
        setattr(package_module, base_name, python_module)
  # if '_errors' not in spec.name:
  
  
  import builtins
  old_import = builtins.__import__
  builtins.__import__ = _import_override
  sys.modules[spec.name] = python_module

  # info(f'spec.origin: {spec.origin}')
  # TODO: Swap out sys.modules.
  assert hasattr(builtins, 'IOError')
  try:
    if hasattr(spec.loader, 'exec_module'):
      spec.loader.exec_module(python_module)
    else:
      del sys.modules[spec.name]
      sys.modules[spec.name] = python_module = spec.loader.load_module(spec.name)
  except ImportError as e:
    info(f'Failed to exec spec: {spec}. {e}')
    del sys.modules[spec.name]
    raise e
  except Exception as e:
    info(f'Failed to exec spec: {spec}. {e}')
    return None
  finally:
    builtins.__import__ = old_import


  return python_module


def get_python_module_from_module_key(module_key, force_reload=False):
  '''Retrieves the python module associated with the provided module_key, reloading if required.

  This will return None if the module could not be loaded or previously failed to load and
  force_reload is not True.'''
  module_already_present = module_key in __module_key_to_python_module
  # Note: We do not reload non-file-based modules.
  if (not force_reload or not module_key.is_loadable_by_file()) and module_already_present:
    return __module_key_to_python_module[module_key]

  # Loosely based on:
  # https://docs.python.org/3/library/importlib.html#approximating-importlib-import-module
  # __module_key_to_python_module[module_key] may be None - so we check.
  if module_already_present and __module_key_to_python_module[module_key]:
    spec = __module_key_to_python_module[module_key].__spec__
    if force_reload:
      del sys.modules[spec.name]
  elif module_key.is_loadable_by_file():
    filename = module_key.get_filename(False)
    fullname, _ = _fullname_and_package_path_from_filename(filename)
    spec = importlib.util.spec_from_file_location(fullname, filename)
    if not spec:
      return None

  try:
    if module_key.is_loadable_by_file():
      python_module = __module_key_to_python_module[module_key] = _import_source_module(spec)
    else:
      name = module_key.id
      assert name[0] != '.'
      python_module = __module_key_to_python_module[module_key] = importlib.import_module(name, package=None)
  except ImportError as e:
    warning(f'Failed to load {spec} - {module_key}. {e}')
    return None
  else:
    return python_module


def _load_normal_module(module_key,
                        *,
                        is_package,
                        unknown_fallback=False,
                        lazy=True,
                        include_graph=False,
                        force_real=False) -> Module:
  assert module_key.module_source_type == ModuleSourceType.NORMAL
  name = module_key.get_basename()
  filename = module_key.get_filename(prefer_stub=not force_real)
  if not os.path.exists(filename):
    if not unknown_fallback:
      raise InvalidModuleError(filename)
    return _create_empty_module(name)
  if lazy:
    return _create_lazy_module(name, filename, is_package=is_package, include_graph=include_graph)

  module = ModuleImpl(name=name,
                      filename=filename,
                      members={},
                      is_package=is_package,
                      module_loader=sys.modules[__name__])

  return module


def _create_lazy_module(name, filename, is_package, include_graph) -> LazyModule:
  return LazyModule(name=name,
                    filename=filename,
                    load_module_exports_from_filename=_load_module_exports_from_filename,
                    is_package=is_package,
                    keep_graph=include_graph or keep_graphs_default,
                    module_loader=sys.modules[__name__])


def _create_empty_module(name):
  return ModuleImpl(
      name=name,
      filename=name,  # TODO
      members={},
      is_package=False,
      module_loader=sys.modules[__name__])


def load_graph_from_module_key(module_key, module=None):
  filename = module_key.get_filename(False)
  with open(filename, 'r') as f:
    source = '\n'.join(f.readlines())
  with FileContext(filename):
    return api.graph_from_source(source, filename, module=module)


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


def module_key_from_relative_module_name(name: str, curr_dir):
  filename = filename_from_relative_module_name(name, curr_dir)
  if filename:
    return ModuleKey.from_filename(filename)
  return None


def filename_from_relative_module_name(name: str, curr_dir):
  assert os.path.exists(curr_dir), "Cannot get relative path w/o knowing current dir."
  relative_path = _relative_path_from_relative_module(name)
  absolute_path = os.path.abspath(os.path.join(curr_dir, relative_path))
  if os.path.exists(absolute_path):
    assert os.path.isdir(absolute_path)
    for name in ('__init__.pyi', '__init__.py'):
      filename = os.path.join(absolute_path, name)
      if os.path.exists(filename):
        return filename
  # Name refer's to a .py[i] module; not a package.
  for file_extension in ('.py', '.pyi'):
    filename = f'{absolute_path}{file_extension}'
    if os.path.exists(filename):
      return filename
  from glob import glob
  compiled_matches = list(glob(f'{absolute_path}.*.so'))
  if compiled_matches:
    if len(compiled_matches) > 1:
      info(f'compiled_matches: {compiled_matches}')
      assert False
    else:
      return compiled_matches[0]
  return None


def module_key_from_name(name: str, curr_dir=None) -> ModuleKey:
  if name[0] == '.':
    module_key = module_key_from_relative_module_name(name, curr_dir)
    if module_key:
      return module_key
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
        filename = spec.loader.get_filename()  # type: ignore
        return ModuleKey.from_filename(filename)
      return ModuleKey(ModuleSourceType.BUILTIN, name)
  debug(f'Could not find Module {name} - falling back to Unknown.')
  return ModuleKey(ModuleSourceType.BAD, name)


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
  if type_str == 'from_import':
    filename = obj
    index = filename.rindex('.')
    module_name = filename[:index]
    object_name = filename[index + 1:]
    return get_pobject_from_module(module_name, object_name, os.path.dirname(filename))
  return False, None


def deserialize(type_str, obj):
  return serialization.deserialize(type_str, obj, hook_fn=deserialize_hook_fn)
