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
from autocomplete.nsn_logging import info

__module_dict = None


def get_module(path: str) -> Module:
  global __module_dict
  if not __module_dict:
    __module_dict = {}
  if path in __module_dict:
    return __module_dict[path]
  module = _load_module(path)
  __module_dict[path] = module
  return module


def _load_module(path: str) -> Module:
  # info(f'Loading module: {path}')
  parts = path.split('.')
  containing_package = None
  for part in parts:
    containing_package = Module(
        module_type=ModuleType.UNKNOWN,
        name=part,
        members={},
        containing_package=containing_package)
  return containing_package
