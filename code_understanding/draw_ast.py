'''A simple module for drawing a line-annotated AST drawing.'''
import ast
import graphviz
from autocomplete.code_understanding.ast_utils import _name_or_id
from autocomplete.code_understanding.utils import type_name
import argparse
import webbrowser

class AstDrawer(ast.NodeVisitor):
  def __init__(self, path='/tmp/ast'):
    self.parent = None
    self.parent_lineno=0
    self.graph = graphviz.Digraph('AST', filename=path)
    self.line_to_nodes = {}


  def generic_visit(self, node):
    # We start indexing at 0 while in the AST it starts at 1, so we shift
    # lineno immediately by 1.
    lineno = node.lineno-1 if hasattr(node, 'lineno') else None
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
    super(AstDrawer, self).generic_visit(node)
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
        print(f'subgraph_name: {subgraph_name}')
        for parent, child in parent_child_pairs:
          name = _name_or_id(child)
          type_name_ = type_name(child)
          if name is not None:
            c.node(str(child), label=f'{name}: ({type_name_})')
          else:
            c.node(str(child), label=f'({type_name_})')
          c.edge(str(parent), str(child))
    if include_source:
      self.graph.node(name=''.join(f'{i}: {line}\l' for i,line in enumerate(lines)), shape='box')

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument("source_file")
  args = parser.parse_args()
  with open(args.source_file) as f:
    source = ''.join(f.readlines())
  tree = ast.parse(source)
  drawer = AstDrawer()
  drawer.visit(tree)
  drawer.create_graph(source)
  drawer.graph.render(drawer.graph.filename)
  webbrowser.get('chrome').open_new_tab('file://' + drawer.graph.filename + '.pdf')
