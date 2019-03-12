import os
from glob import glob
import astor
import ast


class Visitor(ast.NodeVisitor):
  def __init__(self, trie):
    self.trie = trie

  def visit_Assign(self, node):
    self.trie.add(astor.to_source(node))

  def visit_Expr(self, node):
    self.trie.add(astor.to_source(node))

  def visit_Import(self, node):
    self.trie.add(astor.to_source(node))

  def visit_ImportFrom(self, node):
    self.trie.add(astor.to_source(node))

  def visit_For(self, node):
    self.trie.add(astor.to_source(node))
    self.generic_visit(node)

  def visit_FunctionDef(self, node):
    self.trie.add(astor.to_source(node))
    self.generic_visit(node)


# def add_source_to_trie(source_lines, trie):
#   for line in source_lines: # TODO: Make this a statement instead of a line.
#     trie.add(line.strip())

# def add_source_path_to_trie(filepath, trie):
#   with open(filepath, 'r') as f:
#     add_source_to_trie(f.readlines(), trie)

def add_source_to_trie_with_ast(filepath, trie):
  with open(filepath, 'r') as f:
    source = ''.join(f.readlines())
  root = ast.parse(source)
  visitor = Visitor(trie)
  visitor.visit(root)

def add_source_tree_to_trie(path, trie):
  filepaths = glob(os.path.join(path, '**', '*py'), recursive=True)
  for filepath in filepaths:
    add_source_to_trie_with_ast(filepath, trie)
