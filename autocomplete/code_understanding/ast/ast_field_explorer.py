import ast

from ..utils import type_name


class AstFieldExplorer(ast.NodeVisitor):
  def __init__(self):
    self.field_map = {}

  def generic_visit(self, node):
    if type_name(node) not in self.field_map:
      self.field_map[type_name(node)] = list(filter(lambda s: s[0] != '_', dir(node)))
    super(AstFieldExplorer, self).generic_visit(node)
