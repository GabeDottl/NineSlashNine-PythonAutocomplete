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
from autocomplete.code_understanding.typing.language_objects import (Module,
                                                                     ModuleType)
from autocomplete.nsn_logging import info, warning, error
from autocomplete.code_understanding.typing import api
import importlib
import os

__module_dict: dict = {}


def get_module(name: str) -> Module:
  global __module_dict
  if name in __module_dict:
    module = __module_dict[name]
    if module is None:
      error('Circular dep.')
      return _create_unknown_module(name)
    return module
  __module_dict[name] = None
  module = _load_module(name)
  assert module
  __module_dict[name] = module
  return module


def _module_from_source(name, filepath, source) -> Module:
  old_cwd = os.getcwd()
  new_dir = os.path.dirname(filepath)
  info(f'new_dir: {new_dir}')
  os.chdir(new_dir)
  frame_ = api.frame_from_source(source)
  info(f'old_cwd: {old_cwd}')
  os.chdir(old_cwd)

  # name = os.path.split(os.path.basename(path))[0]
  # TODO: containing_package.
  return Module(
      module_type=ModuleType.LOCAL,  # TODO
      name=name,
      filepath=filepath,
      members=frame_._locals,
      containing_package=None)

def _create_unknown_module(name):
  parts = name.split('.')
  containing_package = None
  for part in parts:
    containing_package = Module(
        module_type=ModuleType.UNKNOWN,
        name=part,
        members={},
        containing_package=containing_package)
  return containing_package


def _load_module(name: str) -> Module:
  info(f'Loading module: {name}')
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
      
      with open(path) as f:
        source = ''.join(f.readlines())
      return _module_from_source(name, path, source)
    spec = importlib.util.find_spec(name)
    if spec:
      if spec.has_location:
        path = spec.loader.get_filename()
        with open(path) as f:
          source = ''.join(f.readlines())
        return _module_from_source(name, path, source)
      else:  # System module
        # TODO.
        warning(f'System modules not implemented.')
  except Exception as e:
    warning(e)
  warning(f'Could not find Module {name} - falling back to Unknown.')
  return _create_unknown_module(name)
