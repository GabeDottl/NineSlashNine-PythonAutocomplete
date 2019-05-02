import ast


class AstTypeFinder(ast.NodeVisitor):
  def __init__(self):
    self.target_type = None
    self.target_node = None

  def find_type(self, ast_node, target_type):
    self.target_type = target_type
    self.generic_visit(ast_node)
    tmp = self.target_node
    self.target_node = None
    return tmp

  def generic_visit(self, node):
    if self.target_node is not None:
      return
    if isinstance(node, self.target_type):
      self.target_node = node
      return
    super(AstTypeFinder, self).generic_visit(node)
