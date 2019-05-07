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
import importlib
import os
import pkgutil
from typing import Dict, Set, Tuple

import typeshed
from autocomplete.code_understanding.typing import (api, collector, frame, serialization)
from autocomplete.code_understanding.typing.collector import FileContext
from autocomplete.code_understanding.typing.errors import (LoadingModuleAttributeError, SourceAttributeError,
                                                           UnableToReadModuleFileError)
from autocomplete.code_understanding.typing.expressions import (AugmentedObject, NativeObject)
from autocomplete.code_understanding.typing.language_objects import (
    LazyModule, Module, ModuleImpl, ModuleType, NativeModule, create_main_module)
from autocomplete.code_understanding.typing.pobjects import (NativeObject, PObject, UnknownObject)
from autocomplete.nsn_logging import debug, error, info, warning

__filename_module_dict: Dict[str, Module] = {}
__native_module_dict: Dict[str, Module] = {}
# This is primarily to ensure we never read in a file twice - which should be essentially impossible
# given the public API.
__loaded_paths: Set[str] = set()


class InvalidModuleError(Exception):
  ...


def get_pobject_from_module(module_name: str, pobject_name: str) -> PObject:
  # See if there's a module we can read that'd correspond to the full name.
  # module_name will only end with '.' if it's purely periods- 1 or more. In that
  # case, we don't want to mess things up by adding an additional period at the
  # end of the module name.
  if module_name[-1] == '.':
    full_pobject_name = f'{module_name}{pobject_name}'
  else:
    full_pobject_name = f'{module_name}.{pobject_name}'
  try:
    return AugmentedObject(get_module(full_pobject_name, unknown_fallback=False), imported=True)
  except InvalidModuleError:
    pass

  module = get_module(module_name)
  # Try to get pobject_name as a member of module if module is a package.
  # If the module is already loading, then we don't want to check if pobject_name is in module
  # because it will cause headaches. So try getting full_object_name as a package instead.
  if (not isinstance(module, LazyModule) or not module._loading) and pobject_name in module:
    return AugmentedObject(module[pobject_name], imported=True)

  return UnknownObject(full_pobject_name, imported=True)


def get_module(name: str, unknown_fallback=True, lazy=True, include_graph=False) -> Module:
  filename, is_package, module_type = get_module_info_from_name(name)
  return _get_module_internal(name, filename, is_package, module_type, unknown_fallback, lazy, include_graph)


def get_module_from_filename(name,
                             filename,
                             is_package=False,
                             unknown_fallback=True,
                             lazy=True,
                             include_graph=False) -> Module:
  filename = os.path.abspath(filename)  # Ensure its absolute.
  return _get_module_internal(
      name,
      filename,
      is_package,
      _module_type_from_filename(filename),
      unknown_fallback=unknown_fallback,
      lazy=lazy,
      include_graph=include_graph)


def _get_module_internal(name, filename, is_package, module_type, unknown_fallback, lazy, include_graph):
  if module_type == ModuleType.UNKNOWN_OR_UNREADABLE:
    if unknown_fallback:
      return _create_empty_module(name, module_type)
    raise InvalidModuleError(name)

  global __filename_module_dict
  global __native_module_dict

  # Modules we load natively are stored in a separate dict from the filename dict because they
  # typically don't have a valid filename.
  # TODO: This could get murky if we allowed more modules to be loaded natively.
  if name in NATIVE_MODULE_WHITELIST or module_type == ModuleType.BUILTIN:
    if name in __native_module_dict:
      return __native_module_dict[name]
    out = __native_module_dict[name] = _load_module_from_module_info(
        name,
        filename,
        is_package,
        module_type,
        unknown_fallback=unknown_fallback,
        lazy=lazy,
        include_graph=include_graph)
    return out

  assert filename is not None and os.path.exists(filename)
  assert filename == os.path.abspath(filename)

  # Normal case, check if we have a module for the specified file already.
  if filename in __filename_module_dict:
    module = __filename_module_dict[filename]
    if module is None:  # Oddly enough, a module is allowed to directly invoke itself when it's
      # __main__ at least - see pdb.py where it imports itself when it is the main module.
      if unknown_fallback:
        return _create_empty_module(name, module_type)
      raise InvalidModuleError(name)

    assert module is not None, collector._filename_context

    # Load module if it's not alread loaded and we're specifically retrieving a non-Lazy version.
    if isinstance(module, LazyModule) and not lazy:
      module.load()
      # Even if the module is loaded, it'll still act lazily unless we explicitly indicate not to.
      module.lazy = False
    return module

  # We set this to None to start as a form of dependency-cycle-checking. This is the only way that
  # an object is this dict is None and we check if a value retrieved from it is None above.
  __filename_module_dict[filename] = None

  module = _load_module_from_module_info(
      name,
      filename,
      is_package,
      module_type,
      unknown_fallback=unknown_fallback,
      lazy=lazy,
      include_graph=include_graph)
  assert module is not None
  debug(f'Adding {filename} to module dict.')
  # Note: This will essentially stop us from storing modules which are unreadable because they are
  # sourced from invalid files. That's fine.
  if filename is not None and os.path.exists(filename):
    __filename_module_dict[filename] = module
  return module


def _module_exports_from_source(module, source, filename, return_graph=False) -> Dict[str, PObject]:
  with FileContext(filename):
    debug(f'len(__loaded_paths): {len(__loaded_paths)}')
    a_frame = frame.Frame(module=module, namespace=module, locals=module._members)
    graph = api.graph_from_source(source, module)
    graph.process(a_frame)
  # Normally, exports wouldn't unclude protected members - but, internal members may rely on them
  # when running, so we through them in anyway for the heck of it.
  if return_graph:
    return a_frame._locals, graph
  return a_frame._locals


def _get_module_stub_source_filename(name) -> str:
  '''Retrieves the stub version of a module, if it exists.

  This currently only relies on typeshed, but in the future should also pull from some local repo.'''
  # TODO: local install + TYPESHED_HOME env variable like pytype:
  # https://github.com/google/pytype/blob/309a87fab8a861241823592157208e65c970f7b6/pytype/pytd/typeshed.py#L24
  typeshed_dir = os.path.dirname(typeshed.__file__)
  if name != '.' or name[0] != '.':
    raise ValueError()
  module_path_base = name.replace('.', os.sep)
  for top_level in ('stdlib', 'third_party'):
    # Sorting half to start with the lowest python level, half for consistency across runs.
    # Skip the version-2-only python files.
    for version in filter(lambda x: x != '2', sorted(os.listdir(os.path.join(typeshed_dir, top_level)))):
      for module_path in (os.path.join(module_path_base, "__init__.pyi"), f'{module_path_base}.pyi'):
        abs_module_path = os.path.join(typeshed_dir, top_level, version, module_path)
        if os.path.exists(abs_module_path):
          return abs_module_path, os.path.basename(module_path) == '__init__.pyi'
  raise ValueError(f'Did not find typeshed for {name}')


def load_module_from_source(source, include_graph=False):
  module = create_main_module()
  if include_graph:
    module._members, graph = _module_exports_from_source(
        module, source, filename='__main__', return_graph=True)
    module.graph = graph
  else:
    module._members = _module_exports_from_source(module, source, filename='__main__')
  return module


def _load_module_exports_from_filename(module, filename, return_graph=False):
  try:
    with open(filename) as f:
      source = ''.join(f.readlines())
    info(f'Loading {filename}')
    assert filename not in __loaded_paths
    __loaded_paths.add(filename)
    return _module_exports_from_source(module, source, filename, return_graph=return_graph)
  except UnicodeDecodeError as e:
    warning(f'{filename}: {e}')
    raise UnableToReadModuleFileError(e)


def _module_type_from_filename(filename) -> ModuleType:
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
    for i in range(dot_prefix_count - 1):
      relative_prefix += f'..{os.sep}'
  return f'{relative_prefix}{remaining_name.replace(".", os.sep)}'


def get_module_info_from_name(name: str) -> Tuple[str, bool, ModuleType]:
  try:
    stub_filename, is_package = _get_module_stub_source_filename(name)
    module_type = ModuleType.PUBLIC if 'third_party' in stub_filename else ModuleType.SYSTEM
    return stub_filename, is_package, module_type
  except ValueError:
    pass
  is_package = False
  if name[0] == '.':
    relative_path = _relative_path_from_relative_module(name)
    absolute_path = os.path.abspath(os.path.join(collector.get_current_context_dir(), relative_path))
    if os.path.exists(absolute_path):
      if os.path.isdir(absolute_path):
        is_package = True
        for name in ('__init__.pyi', '__init__.py'):
          filename = os.path.join(collector.get_current_context_dir(), name)
          if os.path.exists(filename):
            return filename, is_package, _module_type_from_filename(filename)
      else:
        assert False
        warning(f'Bizarre case - {absolute_path} is file but not dir...')
        return None, False, ModuleType.UNKNOWN_OR_UNREADABLE
    for file_extension in ('.pyi', '.py'):
      filename = f'{absolute_path}{file_extension}'
      if os.path.exists(filename):
        return filename, False, _module_type_from_filename(filename)
    return '', False, ModuleType.UNKNOWN_OR_UNREADABLE
  try:
    loader = pkgutil.find_loader(name)
  except ImportError as e:
    # find_spec can break for sys modules unexpectedly.
    debug(f'Exception while getting spec for {name}')
    debug(e)
  else:
    if hasattr(loader, 'get_filename'):
      filename = loader.get_filename()
      ext = os.path.splitext(filename)[1]
      if ext != '.pyi' and ext != '.py':
        debug(f'Cannot read module filetype - {filename}')
        return None, False, ModuleType.UNKNOWN_OR_UNREADABLE
      return os.path.abspath(filename), _is_init(filename), _module_type_from_filename(filename)
    return None, False, ModuleType.BUILTIN
  debug(f'Could not find Module {name} - falling back to Unknown.')
  return None, False, ModuleType.UNKNOWN_OR_UNREADABLE


def _load_module(name: str, unknown_fallback=True, lazy=True, include_graph=False) -> Module:
  debug(f'Loading module: {name}')
  filename, is_package, module_type = get_module_info_from_name(name)
  return _load_module_from_module_info(name, filename, is_package, module_type, unknown_fallback, lazy,
                                       include_graph)


NATIVE_MODULE_WHITELIST = set(['six', 're'])


def deserialize_hook_fn(type_str, obj):
  if type_str == NativeModule.__qualname__:
    return True, get_module(obj)
  if type_str == 'import_module':
    name, filename = obj
    return get_module_from_filename(
        name, filename, is_package=_is_init(filename), module_type=_module_type_from_filename(filename))
  if type_str == 'from_import':
    filename = obj
    index = filename.rindex('.')
    module_name = filename[:index]
    object_name = filename[index + 1:]
    return get_pobject_from_module(module_name, object_name)
  return False, None


def deserialize(type_str, obj):
  return serialization.deserialize(type_str, obj, hook_fn=deserialize_hook_fn)


def _load_module_from_module_info(name: str,
                                  filename,
                                  is_package,
                                  module_type,
                                  unknown_fallback=True,
                                  lazy=True,
                                  include_graph=False) -> Module:
  if module_type == ModuleType.UNKNOWN_OR_UNREADABLE:
    if unknown_fallback:
      return _create_empty_module(name, module_type)
    else:
      raise InvalidModuleError(name)

  if module_type == ModuleType.BUILTIN or name in NATIVE_MODULE_WHITELIST:
    # TODO: Create caches and rely on those after initial loads.
    debug(f'name: {name}')
    try:
      python_module = importlib.import_module(name)
    except ImportError:
      return _create_empty_module(name, ModuleType.UNKNOWN_OR_UNREADABLE)
    else:
      return NativeModule(
          name, module_type, filename=filename, native_module=NativeObject(python_module, read_only=True))
  return _load_module_from_filename(
      name, filename, is_package=is_package, module_type=module_type, lazy=lazy, include_graph=include_graph)


def _is_init(filename):
  name = os.path.basename(filename)
  return '__init__.py' in name  # Implicitly includes __init__.pyi.


def _load_module_from_filename(name,
                               filename,
                               *,
                               is_package,
                               module_type=ModuleType.SYSTEM,
                               unknown_fallback=False,
                               lazy=True,
                               include_graph=False) -> Module:
  if not os.path.exists(filename):
    if not unknown_fallback:
      raise InvalidModuleError(filename)
    return _create_empty_module(name, ModuleType.UNKNOWN_OR_UNREADABLE)
  if lazy:
    return _create_lazy_module(
        name, filename, is_package=is_package, module_type=module_type, include_graph=include_graph)

  module = ModuleImpl(
      name=name, module_type=module_type, filename=filename, members={}, is_package=is_package)
  try:
    if include_graph:
      module._members, module.graph = _load_module_exports_from_filename(module, filename, include_graph)
    else:
      module._members = _load_module_exports_from_filename(module, filename)
  except UnableToReadModuleFileError:
    if not unknown_fallback:
      raise InvalidModuleError(filename)
    return _create_empty_module(name, ModuleType.UNKNOWN_OR_UNREADABLE)
  return module


def _create_lazy_module(name, filename, is_package, module_type, include_graph) -> LazyModule:
  return LazyModule(
      name=name,
      module_type=module_type,
      filename=filename,
      load_module_exports_from_filename=_load_module_exports_from_filename,
      is_package=is_package,
      keep_graph=include_graph)


def _create_empty_module(name, module_type):
  return ModuleImpl(
      name=name,
      module_type=module_type,
      filename=name,  # TODO
      members={},
      is_package=False)
