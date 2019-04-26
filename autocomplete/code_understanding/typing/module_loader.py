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
from typing import Dict, Tuple

from autocomplete.code_understanding.typing import api, collector, frame
from autocomplete.code_understanding.typing.collector import FileContext
from autocomplete.code_understanding.typing.errors import (
    LoadingModuleAttributeError, SourceAttributeError,
    UnableToReadModuleFileError)
from autocomplete.code_understanding.typing.expressions import NativeObject
from autocomplete.code_understanding.typing.language_objects import (
    LazyModule, Module, ModuleImpl, ModuleType, NativeModule, create_main_module
)
from autocomplete.code_understanding.typing.pobjects import (
    PObject, UnknownObject)
from autocomplete.nsn_logging import debug, error, info, warning

__module_dict: dict = {}
__path_module_dict: dict = {}


class InvalidModuleError(Exception):
  ...


def get_pobject_from_module(module_name: str, pobject_name: str) -> PObject:
  full_pobject_name = f'{module_name}.{pobject_name}'
  if full_pobject_name in __module_dict:
    return __module_dict[full_pobject_name]

  module = get_module(module_name)

  # Try to get pobject_name as a member of module if module is a package.
  # If the module is already loading, then we don't want to check if pobject_name is in module
  # because it will cause headaches. So try getting full_object_name as a package instead.
  if (not isinstance(module, LazyModule) or
      not module._loading) and pobject_name in module:
    return module[pobject_name]

  # # See if there's a module we can read that'd correspond to the full name.
  try:
    return load_module(full_pobject_name, unknown_fallback=False)
  except InvalidModuleError:
    return UnknownObject(full_pobject_name)


def get_module(name: str, unknown_fallback=True) -> Module:
  global __module_dict
  if name in __module_dict:
    module = __module_dict[name]
    if module is None:
      error('Circular dep.')
      return _create_empty_module(name, ModuleType.UNKNOWN_OR_UNREADABLE)
    return module
  __module_dict[name] = None
  path, is_package, module_type = _module_info_from_name(name)
  module = _load_module_from_module_info(name, path, is_package, module_type)
  module = load_module(name)
  assert module is not None
  info(f'Added {name} to module dict.')
  __module_dict[name] = module
  if path and os.path.exists(path):
    __path_module_dict[path] = module
  return module


def get_module_from_filename(name, filename, is_package=False) -> Module:
  abs_path = os.path.abspath(filename)
  if abs_path in __path_module_dict:
    return __path_module_dict[abs_path]
  module = load_module_from_filename(name, filename, is_package=is_package)
  __path_module_dict[abs_path] = module
  return module


def _module_exports_from_source(module, source, filename) -> Dict[str, PObject]:
  try:
    with FileContext(filename):
      a_frame = frame.Frame(
          module=module, namespace=module, locals=module._members)
      graph = api.graph_from_source(source, module)
      graph.process(a_frame)
  except Exception as e:
    import traceback
    traceback.print_tb(e.__traceback__)
    print(e)
    raise e
  # Normally, exports wouldn't unclude protected members - but, internal members may rely on them
  # when running, so we through them in anyway for the heck of it.
  return a_frame._locals  #dict(filter(lambda kv: '_' != kv[0][0], a_frame._locals.items()))


def _get_module_stub_source_filename(name) -> str:
  '''Retrieves the stub version of a module, if it exists.
  
  This currently only relies on typeshed, but in the future should also pull from some local repo.'''
  # TODO: local install + TYPESHED_HOME env variable like pytype:
  # https://github.com/google/pytype/blob/309a87fab8a861241823592157208e65c970f7b6/pytype/pytd/typeshed.py#L24
  import typeshed
  typeshed_dir = os.path.dirname(typeshed.__file__)
  # basename = name.split('.')[0]
  if name != '.' or name[0] != '.':
    raise ValueError()
  module_path_base = name.replace('.', os.sep)
  for top_level in ('stdlib', 'third_party'):
    # Sorting half to start with the lowest python level, half for consistency across runs.
    # Skip the version-2-only python files.
    for version in filter(
        lambda x: x != '2',
        sorted(os.listdir(os.path.join(typeshed_dir, top_level)))):
      for module_path in (os.path.join(module_path_base, "__init__.pyi"),
                          f'{module_path_base}.pyi'):
        abs_module_path = os.path.join(typeshed_dir, top_level, version,
                                       module_path)
        # info(abs_module_path)
        if os.path.exists(abs_module_path):
          # info(f'Found typeshed path for {name}: {abs_module_path}')
          return abs_module_path, os.path.basename(
              module_path) == '__init__.pyi'
  raise ValueError(f'Did not find typeshed for {name}')


def load_module_from_source(source):
  module = create_main_module()
  module._members = _module_exports_from_source(
      module, source, filename='__main__')
  return module


def load_module_exports_from_filename(module, filename):
  try:
    with open(filename) as f:
      source = ''.join(f.readlines())
    info(f'Loading {module.name}')
    return _module_exports_from_source(module, source, filename)
  except UnicodeDecodeError as e:
    warning(f'{filename}: {e}')
    raise UnableToReadModuleFileError(e)


def _module_type_from_path(path) -> ModuleType:
  for third_party in ('dist-packages', 'site-packages'):
    if third_party in path:
      return ModuleType.PUBLIC
  return ModuleType.SYSTEM


def _relative_path_from_relative_module(name):
  # assert name[0] == '.'

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


def _module_info_from_name(name: str) -> Tuple[str, bool, ModuleType]:
  try:
    stub_path, is_package = _get_module_stub_source_filename(name)
    module_type = ModuleType.PUBLIC if 'third_party' in stub_path else ModuleType.SYSTEM
    return stub_path, is_package, module_type
  except ValueError:
    pass
  is_package = False
  if name[0] == '.':
    relative_path = _relative_path_from_relative_module(name)
    absolute_path = os.path.join(collector.get_current_context_dir(),
                                 relative_path)
    if os.path.exists(absolute_path):
      if os.path.isdir(absolute_path):
        is_package = True
        for name in ('__init__.pyi', '__init__.py'):
          filename = os.path.join(collector.get_current_context_dir(), name)
          if os.path.exists(filename):
            return filename, is_package, _module_type_from_path(filename)
      else:
        warning(f'Bizarre case - {absolute_path} is file but not dir...')
        return None, False, ModuleType.UNKNOWN_OR_UNREADABLE
    for file_extension in ('.pyi', '.py'):
      filename = f'{absolute_path}{file_extension}'
      if os.path.exists(filename):
        return filename, False, _module_type_from_path(filename)
    return '', False, ModuleType.UNKNOWN_OR_UNREADABLE
  try:
    spec = importlib.util.find_spec(name)
  except (AttributeError, ModuleNotFoundError, ValueError) as e:
    # find_spec can break for sys modules unexpectedly.
    debug(f'Exception while getting spec for {name}')
    debug(e)
  else:
    if spec:
      if spec.has_location:
        path = spec.loader.get_filename()
        ext = os.path.splitext(path)[1]
        if ext != '.pyi' and ext != '.py':
          debug(f'Cannot read module filetype - {path}')
          return None, False, ModuleType.UNKNOWN_OR_UNREADABLE
        return path, _is_init(path), _module_type_from_path(path)
      else:  # System module
        return None, False, ModuleType.BUILTIN
  debug(f'Could not find Module {name} - falling back to Unknown.')
  return None, False, ModuleType.UNKNOWN_OR_UNREADABLE


def load_module(name: str, unknown_fallback=True, lazy=True) -> Module:
  debug(f'Loading module: {name}')
  path, is_package, module_type = _module_info_from_name(name)
  return _load_module_from_module_info(name, path, is_package, module_type,
                                       unknown_fallback, lazy)


NATIVE_MODULE_WHITELIST = set(['six', 're'])


def _load_module_from_module_info(name: str,
                                  path,
                                  is_package,
                                  module_type,
                                  unknown_fallback=True,
                                  lazy=True) -> Module:
  if module_type == ModuleType.UNKNOWN_OR_UNREADABLE:
    if unknown_fallback:
      return _create_empty_module(name, module_type)
    else:
      raise InvalidModuleError(name)

  if module_type == ModuleType.BUILTIN or name in NATIVE_MODULE_WHITELIST:
    # TODO: Create caches and rely on those after initial loads.
    python_module = importlib.import_module(name)
    return NativeModule(
        name,
        module_type,
        filename=path,
        native_module=NativeObject(python_module))
  return load_module_from_filename(
      name, path, is_package=is_package, module_type=module_type, lazy=lazy)


def _is_init(path):
  name = os.path.basename(path)
  return '__init__.py' in name  # include .pyi


def load_module_from_filename(name,
                              filename,
                              *,
                              is_package,
                              module_type=ModuleType.SYSTEM,
                              unknown_fallback=False,
                              lazy=True) -> Module:
  if not os.path.exists(filename):
    if not unknown_fallback:
      raise InvalidModuleError(filename)
    else:
      return _create_empty_module(name, ModuleType.UNKNOWN_OR_UNREADABLE)
  if lazy:
    return _create_lazy_module(
        name, filename, is_package=is_package, module_type=module_type)

  module = ModuleImpl(
      name=name,
      module_type=module_type,
      filename=filename,
      members={},
      is_package=is_package)
  module._members = load_module_exports_from_filename(module, filename)
  return module


def _create_lazy_module(name, filename, is_package, module_type) -> LazyModule:
  return LazyModule(
      name=name,
      module_type=module_type,
      filename=filename,
      load_module_exports_from_filename=load_module_exports_from_filename,
      is_package=is_package)


def _create_empty_module(name, module_type):
  return ModuleImpl(
      name=name,
      module_type=module_type,
      filename=name,  # TODO
      members={},
      is_package=False)
