'''A utility module for deriving information about a project's modules.

module_infos = module_info.get_module_infos_for_path('jedi')
modules = module_info.load_modules_from_module_infos(module_infos)
df = module_info.create_dataframe_summary_of_modules(modules)
utils.display_df_in_browser(df)
'''

import importlib
import inspect
import os
import pkgutil
import sys
from collections import namedtuple

import pandas as pd


def get_module_infos_for_path(path, filter_list=None):
  out = []
  if isinstance(filter_list, str):
    filter_list = (filter_list,)

  for module_info in pkgutil.iter_modules([path]):
    if module_info.ispkg:
      pkg = os.path.join(module_info.module_finder.path, module_info.name)
      filter_match = False
      if filter_list:
        for f in filter_list:
          if f in pkg:
            print(f'{pkg} contains {f} - skipping')
            filter_match = True
            break

      if not filter_match:
        out += get_module_infos_for_path(pkg)
    else:
      out.append(module_info)
  return out


def _is_public_func_or_class(name, member):
  if name[0] == '_':
    return False
  return inspect.isclass(member) or inspect.isfunction(member)


def load_modules_from_module_infos(module_infos):
  modules = []
  for mi in module_infos:
    sys.path.insert(0, os.path.abspath(mi.module_finder.path))
    modules.append(importlib.import_module(mi.name))
    sys.path.pop(0)
  return modules


def create_dataframe_summary_of_modules(modules):
  columns = ('module', 'member_name', 'member', 'type', 'module_path')
  MemberInfo = namedtuple('MemberInfo', columns)
  mi = MemberInfo(*([] for _ in columns))
  for module in modules:
    for member_name, member in filter(lambda x: _is_public_func_or_class(*x),
                                      inspect.getmembers(module)):
      mi.module.append(module.__name__)
      mi.member_name.append(member_name)
      mi.member.append(member)
      mi.type.append(type(member))
      mi.module_path.append(module.__file__)
  return pd.DataFrame(mi._asdict())
