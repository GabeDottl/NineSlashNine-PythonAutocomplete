import ast
import glob
import importlib
import itertools
import os
import webbrowser

import _ast
import graphviz
import pandas as pd
from .ast.ast_utils import _name_id_or_arg
# from .reference_ast_node_visitor import (ReferenceAstNodeVisitor)
from .utils import *
from ..nsn_logging import *


def get_all_py_files(path, recursive=True):
  if recursive:
    return glob.glob(os.path.join(path, '**', '*py'))
  return glob.glob(os.path.join(path, '*py'))


def get_module_name_from_filepath(path):
  # Remove .py extension and replace path separators with dots.
  return os.path.splitext(path)[0].replace('/', '.')


def get_unexecuted_module_from_filepath(path):
  '''Retrieves an unloaded module using the provided path.

  This is mostly useless unless you are going to load the module.
  It does provide a little utility in creating the appropriate
  module path.
  '''
  module_name = get_module_name_from_filepath(path)
  spec = importlib.util.spec_from_file_location(module_name, path)
  module = importlib.util.module_from_spec(spec)
  return module  # spec.loader.exec_module(module)


def join_names(a, b):
  if a is None:
    return b
  if b is None:
    return a
  if a == '' or b == '':
    return a + b
  return f'{a}.{b}'


def _get_complete_attribute_path(node, suffix=''):
  if isinstance(node.value, _ast.Attribute):
    return _get_complete_attribute_path(node.value, suffix=join_names(node.attr, suffix))
  # assert isinstance(node.value, _ast.Name)
  if isinstance(node.value, _ast.Call):
    return join_names(node.value.func, join_names(node.attr, suffix))
  # print(type_name(node))
  return join_names(node.value.id, join_names(node.attr, suffix))


def get_statistics_about_python_source(path, source=None, shorten_path=True):
  # tree = ast.parse(source)
  traveler = ReferenceAstNodeVisitor(path, source)
  # traveler.current_module_name = module_name
  traveler.traverse()
  source = traveler.module_source
  # return traveler.nodes
  columns = ['path', 'type', 'name', 'complete_name', 'lineno', 'node', 'parent']
  values = list(zip(itertools.repeat(path, len(traveler.nodes)), *zip(*traveler.nodes)))

  df = pd.DataFrame(values, columns=columns)
  _append_code(df, source)
  df = df.sort_values('lineno')
  if shorten_path:
    df = _shorten_paths_in_df(df)
  return df, traveler


def get_statistics_about_project(path):
  python_filenames = get_all_py_files(path)
  out_df = None
  for filename in python_filenames:
    with open(filename) as f:
      source = ''.join(f.readlines())
    df = get_statistics_about_python_source(source, filename)
    if out_df is None:
      out_df = df
    else:
      out_df = out_df.append(df)
  if out_df is not None:
    out_df = out_df.reset_index(level=0).drop(columns='index')
  return out_df


def _append_code(df, source):
  lines = source.splitlines()
  df['code'] = pd.Series([lines[int(index - 1)] if index == index else '' for index in df['lineno'].values],
                         df.index)
  return df


def _shorten_paths_in_df(df):
  df['path'] = df['path'].apply(shorten_path)
  return df
