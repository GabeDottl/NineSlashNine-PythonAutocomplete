'''This module handles 'loading'/importing modules found in analyzing source.

We're of course not actually loading the module in the traditional sense.
Instead, we're doing one of a few things:

1) Generating a Module instance from an actual source file including a full
CFG.
2) Generating a Module instance from an interface stub file (which we may have
created) and returning types.
3) If we can't find a module that's imported, we will create an 'Unknown'
module.
'''
import importlib
import os
from typing import Dict

from autocomplete.code_understanding.typing import api, collector, frame
from autocomplete.code_understanding.typing.collector import FileContext
from autocomplete.code_understanding.typing.errors import (
    LoadingModuleAttributeError, SourceAttributeError)
from autocomplete.code_understanding.typing.language_objects import (LazyModule,
                                                                     Module,
                                                                     ModuleType)
from autocomplete.code_understanding.typing.pobjects import (PObject,
                                                             UnknownObject)
from autocomplete.nsn_logging import (debug, error, pop_context, push_context,
                                      warning)

__module_dict: dict = {}
__path_module_dict: dict = {}


class InvalidModuleError(Exception):
  ...


def get_pobject_from_module(module_name: str, pobject_name: str) -> PObject:
  module = get_module(module_name)
  # pobject_name may correspond to a module - try getting it.
  full_pobject_name = f'{module_name}.{pobject_name}'
  if module.is_package and pobject_name not in module:
    try:
      return get_module(full_pobject_name, unknown_fallback=False)
    except InvalidModuleError:
      warning(f'Failed to import pobject from module: {full_pobject_name}')
      return UnknownObject(full_pobject_name)
  try:
    return module[pobject_name]
  except (SourceAttributeError, LoadingModuleAttributeError):
    return UnknownObject(full_pobject_name)


def get_module(name: str, unknown_fallback=True) -> Module:
  global __module_dict
  if name in __module_dict:
    module = __module_dict[name]
    if module is None:
      error('Circular dep.')
      return _create_unknown_module(name)
    return module
  __module_dict[name] = None
  module = load_module(name)
  assert module
  __module_dict[name] = module
  __path_module_dict[os.path.abspath(module.filename)] = module
  return module


def get_module_from_filename(name, filename, is_package=False) -> Module:
  abs_path = os.path.abspath(filename)
  if abs_path in __path_module_dict:
    return __path_module_dict[abs_path]
  module = load_module_from_filename(name, filename, is_package=is_package)
  __path_module_dict[abs_path] = module
  return module


def _module_exports_from_source(module, source, filename) -> Dict[str, PObject]:
  # old_cwd = os.getcwd()
  # new_dir = os.path.dirname(filename)
  # debug(f'new_dir: {new_dir}')
  # os.chdir(new_dir)
  push_context(os.path.basename(filename))
  with FileContext(filename):
    a_frame = frame.Frame(namespace=module, locals=module._members)
    graph = api.graph_from_source(source)
    graph.process(a_frame)
  pop_context()
  # debug(f'old_cwd: {old_cwd}')
  # os.chdir(old_cwd)
  return dict(filter(lambda kv: '_' != kv[0][0], a_frame._locals.items()))


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


def load_module_exports_from_filename(module, filename):
  try:
    with open(filename) as f:
      source = ''.join(f.readlines())
    return _module_exports_from_source(module, source, filename)
  except UnicodeDecodeError as e:
    warning(f'{filename}: {e}')
    raise ValueError(e)


def load_module(name: str, unknown_fallback=True, lazy=True) -> Module:
  debug(f'Loading module: {name}')
  try:
    stub_path, is_package = _get_module_stub_source_filename(name)
    return load_module_from_filename(
        name, stub_path, is_package=is_package, lazy=lazy)
  except ValueError:
    pass
  is_package = False
  if name[0] == '.':
    if name == '.':
      # TODO: Weird getting this from a collector... state.py?
      path = os.path.join(collector.get_current_context_dir(), '__init__.py')
      is_package = True
    else:
      path = f'{collector.get_current_context_dir()}.{name.replace(".", os.sep)}'
      if os.path.isdir(path):
        path = os.path.join(path, '__init__.py')
        is_package = True
      else:
        path = f'{path}.py'

    load_module_from_filename(name, path, is_package=is_package, lazy=lazy)
  try:
    spec = importlib.util.find_spec(name)
    if spec:
      if spec.has_location:
        path = spec.loader.get_filename()
        return load_module_from_filename(
            name, path, is_package=_is_init(path), lazy=lazy)
      else:  # System module
        # TODO.
        warning(f'System modules not implemented.')
  except (AttributeError, ModuleNotFoundError) as e:
    # find_spec can break for sys modules unexpectedly.
    warning(f'Exception while getting spec for {name}')
    warning(e)
  if not unknown_fallback:
    raise InvalidModuleError(name)
  warning(f'Could not find Module {name} - falling back to Unknown.')
  return _create_unknown_module(name)


def _is_init(path):
  name = os.path.basename(path)
  return '__init__.py' in name  # include .pyi


def load_module_from_filename(name,
                              filename,
                              *,
                              is_package,
                              unknown_fallback=False,
                              lazy=True) -> Module:
  if not os.path.exists(filename):
    if not unknown_fallback:
      raise InvalidModuleError(filename)
    else:
      return _create_unknown_module(name)
  if lazy:
    return _create_lazy_module(name, filename, is_package=is_package)

  module = Module(
      module_type=ModuleType.LOCAL,  # TODO
      name=name,
      filename=filename,
      members={},
      containing_package=None,
      is_package=is_package)
  module._members = load_module_exports_from_filename(module, filename)
  # name = os.path.splitext(os.path.basename(path))[0]
  # TODO: containing_package.
  return module


def _create_lazy_module(name, filename, is_package) -> LazyModule:
  return LazyModule(
      module_type=ModuleType.LOCAL,  # TODO
      name=name,
      members={},
      filename=filename,
      load_module_exports_from_filename=load_module_exports_from_filename,
      containing_package=None,
      is_package=is_package)


def _create_unknown_module(name):
  parts = name.split('.')
  containing_package = None
  for part in parts:
    containing_package = Module(
        module_type=ModuleType.UNKNOWN,
        name=part,
        members={},
        filename=name,  # TODO
        containing_package=containing_package,
        is_package=False)
  return containing_package
