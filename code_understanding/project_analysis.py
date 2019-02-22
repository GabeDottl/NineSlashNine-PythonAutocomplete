import ast
import _ast
import webbrowser
import glob
import os
from autocomplete.nsn_logging import *
from autocomplete.code_understanding.utils import *
from autocomplete.code_understanding.ast_utils import *
import importlib
import pandas as pd
import itertools
import graphviz

# def bucketize_ast(ast, out=None):
#   class Traveler(ast.NodeVisitor):
#
#   if out is None:
#     out = {}


def get_all_py_files(path, recursive=True):
  if recursive:
    return glob.glob(os.path.join(path, '**', '*py'))
  return glob.glob(os.path.join(path, '*py'))


def get_module_name_from_filepath(path):
  # Remove .py extension and replace path separators with dots.
  return os.path.splitext(path)[0].replace('/', '.')


def get_unexecuted_module_from_filepath(path):
  module_name = get_module_name_from_filepath(path)
  spec = importlib.util.spec_from_file_location(module_name, path)
  module = importlib.util.module_from_spec(spec)
  return module  # spec.loader.exec_module(module)


class AstFieldExplorer(ast.NodeVisitor):

  def __init__(self):
    self.field_map = {}

  def generic_visit(self, node):
    if type_name(node) not in self.field_map:
      self.field_map[type_name(node)] = list(
          filter(lambda s: s[0] != '_', dir(node)))
    super(AstFieldExplorer, self).generic_visit(node)


def _complete_name(node, node_to_parent_dict, base_name='', descendents=set()):
  if node is None:
    return ''
  parent = node_to_parent_dict[node] if node in node_to_parent_dict else None
  if parent in descendents:
    # print(f'loop({parent}): {descendents}')
    return base_name

  def join(a, b):
    if a is None:
      return b
    if b is None:
      return a
    if a == '' or b == '':
      return a + b
    return f'{a}.{b}'

  name = _name_or_id(node)
  name = join(name, base_name)

  # descendents = set() if descendents is None else descendents
  descendents.add(node)
  if parent is not None:
    return _complete_name(parent, node_to_parent_dict, base_name=name, descendents=descendents)
  return name

def _find_matching_name(id, names_in_scope):
  if id is None:
    return None
  for name, complete_name in names_in_scope:
    if id == name:
      return complete_name
  return None






class AstTraverser(ast.NodeVisitor):

  def __init__(self):
    self.type_to_nodes = {}
    self.node_to_parent = {}
    self.parent = 'None'
    self.names_to_node = {}
    self.names_in_scope = []

  def _extract_fields(self, node):
    name = _name_or_id(node)
    lineno = node.lineno if hasattr(node, 'lineno') else None
    # id = node.id if hasattr(node, 'id') else None
    reference = _find_matching_name(name, self.names_in_scope)
    parent_name = self.parent.name if hasattr(self.parent, 'name') else None
    return name, lineno, reference, parent_name

  def generic_visit(self, node):
    if type_name(node) not in self.type_to_nodes:
      arr = []
      self.type_to_nodes[type_name(node)] = arr
    else:
      arr = self.type_to_nodes[type_name(node)]

    name, lineno, reference, parent_name = self._extract_fields(node)
    if name is not None:
      if node == self.parent:
        print(f'{node} is own parent')
      elif node not in self.node_to_parent:
        self.node_to_parent[node] = self.parent
      else:
        print(f'{node} has existing parent {_name_or_id(self.node_to_parent[node])} compared to {_name_or_id(self.parent)}')

    # TODO: Handle '_ast.Store' - for x in y case.
    if name is not None:
      complete_name = _complete_name(node, self.node_to_parent)
      print(f'{name}: {complete_name}')
      self.names_to_node[complete_name] = node
      self.names_in_scope.insert(0, (name, complete_name))

    arr.append((name, lineno, reference, node, self.parent, parent_name))
    real_parent = _name_or_id(node) is not None and (hasattr(node, 'body') or hasattr(node, 'targets'))
    if real_parent:
      old_parent = self.parent
      self.parent = node
      # If the node is a function, then any variables defined within should
      # fall out of scope. Otherwise, they'll stay.
      # https://www.geeksforgeeks.org/scope-resolution-in-python-legb-rule/
    if isinstance(node, _ast.FunctionDef):
      field_count = len(self.names_in_scope)
      # if hasattr(node.body, '__iter__'):
      #   for body_node in node.body:
      #     self.generic_visit(body_node)
      # else:
      #   self.generic_visit(node.body)
    super(AstTraverser, self).generic_visit(node)
    if isinstance(node, _ast.FunctionDef):
        # Remove any fields that were added from the current body
      self.names_in_scope = self.names_in_scope[-field_count:]
    if real_parent:
      self.parent = old_parent
    # else:
    #   super(AstTraverser, self).generic_visit(node)

    # Assignment operations should add to the list of names, but only after
    # processing the contents of the right side above - hence putting this
    # down here.
    # if isinstance(node, _ast.Assign):
    #   for target in node.targets:
    #     complete_name = _complete_name(target, self.node_to_parent)
    #     print(f'{name}: {complete_name}')
    #     self.names_to_node[complete_name] = target
    #     self.names_in_scope.insert(0, (name, complete_name))
    # else:
    #   super(AstTraverser, self).generic_visit(node)


def get_statistics_about_python_source(source, path):
  tree = ast.parse(source)
  traveler = AstTraverser()
  traveler.visit(tree)
  # return traveler.type_to_nodes
  columns = [
      'path', 'type', 'name', 'lineno', 'reference', 'node', 'parent', 'parent_name'
  ]
  values = list(
      itertools.chain(*list(
          list(
              zip(
                  itertools.repeat(path, len(nodes)),
                  itertools.repeat(t, len(nodes)), *zip(*nodes)))
          for t, nodes in traveler.type_to_nodes.items())))

  df = pd.DataFrame(values, columns=columns)
  append_code(df, source)
  df = df.sort_values('lineno')
  return df


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


def append_code(df, source):
  lines = source.splitlines()
  df['code'] = pd.Series([
      lines[int(index - 1)] if index == index else ''
      for index in df['lineno'].values
  ], df.index)
  return df


def shorten_paths_in_df(df):
  df['path'] = df['path'].apply(shorten_path)
  return df


# def simple_reference_count(df):
# names = df['name'].
