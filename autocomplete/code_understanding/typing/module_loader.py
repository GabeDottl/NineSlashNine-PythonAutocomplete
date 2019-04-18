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

from autocomplete.code_understanding.typing import api
from autocomplete.code_understanding.typing.language_objects import (LazyModule,
                                                                     Module,
                                                                     ModuleType)
from autocomplete.code_understanding.typing.pobjects import PObject
from autocomplete.nsn_logging import (debug, error, pop_context, push_context,
                                      warning)

__module_dict: dict = {}
__path_module_dict: dict = {}


def get_module(name: str) -> Module:
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
  __path_module_dict[module.filename] = module
  return module


def get_module_from_filename(name, filename) -> Module:
  try:
    return __path_module_dict[os.path.abspath(filename)]
  except KeyError:
    pass
  module = load_module_from_filename(name, filename)
  __path_module_dict[module.filename] = module
  return module


def _module_exports_from_source(source, filename) -> Dict[str, PObject]:
  old_cwd = os.getcwd()
  new_dir = os.path.dirname(filename)
  debug(f'new_dir: {new_dir}')
  os.chdir(new_dir)
  push_context(os.path.basename(filename))
  frame_ = api.frame_from_source(source)
  pop_context()
  debug(f'old_cwd: {old_cwd}')
  os.chdir(old_cwd)
  return dict(filter(lambda kv: '_' != kv[0][0], frame_._locals.items()))


def _create_unknown_module(name):
  parts = name.split('.')
  containing_package = None
  for part in parts:
    containing_package = Module(
        module_type=ModuleType.UNKNOWN,
        name=part,
        members={},
        filename=name,  # TODO
        containing_package=containing_package)
  return containing_package


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
          return abs_module_path
  raise ValueError(f'Did not find typeshed for {name}')


def load_module_exports_from_filename(filename):
  try:
    with open(filename) as f:
      source = ''.join(f.readlines())
    return _module_exports_from_source(source, filename)
  except UnicodeDecodeError as e:
    warning(f'{filename}: {e}')
    raise ValueError(e)


def load_module_from_filename(name, filename, lazy=True) -> Module:
  if lazy:
    return _create_lazy_module(name, filename)

  exports = load_module_exports_from_filename(filename)
  # name = os.path.splitext(os.path.basename(path))[0]
  # TODO: containing_package.
  return Module(
      module_type=ModuleType.LOCAL,  # TODO
      name=name,
      filename=filename,
      members=exports,
      containing_package=None)


def _create_lazy_module(name, filename) -> LazyModule:
  return LazyModule(
      module_type=ModuleType.LOCAL,  # TODO
      name=name,
      members={},
      filename=filename,
      load_module_exports_from_filename=load_module_exports_from_filename,
      containing_package=None)


def load_module(name: str, lazy=True) -> Module:
  debug(f'Loading module: {name}')
  try:
    stub_path = _get_module_stub_source_filename(name)
    return load_module_from_filename(name, stub_path, lazy)
  except ValueError:
    pass
  try:
    if name[0] == '.':
      if name == '.':
        path = os.path.join(os.getcwd(), '__init__.py')
      else:
        path = f'.{name.replace(".", os.sep)}'
        if os.path.isdir(path):
          path = os.path.join(path, '__init__.py')
        else:
          path = f'{path}.py'

      load_module_from_filename(name, path, lazy)
    spec = importlib.util.find_spec(name)
    if spec:
      if spec.has_location:
        path = spec.loader.get_filename()
        return load_module_from_filename(name, path, lazy)
      else:  # System module
        # TODO.
        warning(f'System modules not implemented.')
  except Exception as e:
    warning(e)
  warning(f'Could not find Module {name} - falling back to Unknown.')
  return _create_unknown_module(name)
