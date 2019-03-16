'''A simple module for drawing a line-annotated Parso-tree drawing.

Basic reference:
https://graphviz.readthedocs.io/en/stable/examples.html
'''
import re
import parso
import graphviz
from autocomplete.code_understanding.ast.ast_utils import _name_id_or_arg
from autocomplete.code_understanding.utils import type_name
import argparse
import webbrowser

class ParsoDrawer:
  def __init__(self, path='/tmp/parso'):
    self.parent = None
    self.parent_lineno=0
    self.graph = graphviz.Digraph('Parso', filename=path)
    self.line_to_nodes = {}


  def traverse(self, node):
    # We start indexing at 0 while in the AST it starts at 1, so we shift
    # lineno immediately by 1.
    lineno = node.get_start_pos_prefix()[0] if hasattr(node, 'get_start_pos_prefix') else None
    lineno = lineno if lineno is not None else self.parent_lineno
    if lineno in self.line_to_nodes:
      arr = self.line_to_nodes[lineno]
    else:
      arr = []
      self.line_to_nodes[lineno] = arr
    arr.append((self.parent, node))
    old_parent = self.parent
    old_parent_lineno = self.parent_lineno
    self.parent = node
    self.parent_lineno = lineno
    try:
      for child in node.children:
        self.traverse(child)
    except AttributeError:
      pass
    self.parent = old_parent
    self.parent_lineno = old_parent_lineno

  def create_graph(self, source, include_source=True):
    lines = source.splitlines()
    for lineno, parent_child_pairs in self.line_to_nodes.items():

      with self.graph.subgraph(name=f'cluster_{lineno}') as c:
        subgraph_name = f'{lineno}: {lines[int(lineno)]}' if lineno is not None else 'None'
        c.attr(label=subgraph_name)
        # c.node_attr.update(style='filled', color='white')
        c.attr(color='blue')
        # print(f'subgraph_name: {subgraph_name}')
        for parent, child in parent_child_pairs:
          try:
            name = child.name.value
          except AttributeError:
            name = str(child)
          type_name_ = child.type
          name = name.replace('<', '').replace('>', '')
          type_name_ = type_name_.replace('<', '').replace('>', '')
          if name is not None:
            c.node(str(child), label=f'{name}: ({type_name_})')
          else:
            c.node(str(child), label=f'({type_name_})')
          c.edge(str(parent), str(child))
    if include_source:
      # We use '\l' instead of \n for left-justified lines:
      # http://www.graphviz.org/doc/info/attrs.html#k:escString
      self.graph.node(name=''.join(f'{i}: {line}\l' for i,line in enumerate(lines)), shape='box')

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument("source_file")
  args = parser.parse_args()
  with open(args.source_file) as f:
    source = ''.join(f.readlines())
  tree = parso.parse(source)
  drawer = ParsoDrawer()
  drawer.traverse(tree)
  drawer.create_graph(source)
  drawer.graph.render(drawer.graph.filename)
  webbrowser.get('chrome').open_new_tab('file://' + drawer.graph.filename + '.pdf')
