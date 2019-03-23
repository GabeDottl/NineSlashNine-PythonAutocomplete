import att

# Each statement is a node, each linear group is a subgraph?
#
# When control flow is hit, a branch is created.
#
# a = 1 # n1
# b = a + 2 # n2
# if True: #n3
#   b = 'asdf' # n4
# else: b = True # n5
# c = 3 # n6
# # n1 -> n2 -> n3
# #                -> n4
# #                     -> n6
# #                -> n5
# #                     -> n6
#
# DFS down tree to node to determine values
# - Memoize where possible + shortcut



# Node creation:
class CFGNode:
  def process(self, node_to_reference_dict):
    raise NotImplementedError() # abstract

@attr.s
class StmtCFGNode(CFGNode):
  assignment = attr.ib() # ?

  def __attrs_post_init__(self):
    self.children = []

  def id(self):
    return self.__hash__()

  def process(self, node_to_reference_dict):
    passz


@attr.s
class IfCFGNode(CFGNode):

  def __attrs_post_init__(self):
    self.children = []

  def id(self):
    return self.__hash__()

def is_linear_collection(type_str):
  return type_str == 'file_input' or type_str == 'suite' or type_str == 'classdef' or type_str == 'with_stmt'


# def create_CFG(node):
#   if node.type == 'simple_stmt':
#     return CFGNode(node)
#   elif is_linear_collection(node.tye):
#     parent = None
#     for child in node.children:
#       node = create_CFG(child)
#       if parent not is None:
#         parent.children.append(node)
#       parent = node
#   elif node.type == 'funcdef':
#     self.handle_funcdef(node)
#   elif node.type == 'decorated':
#     # TODO: Handle decorators.
#     self.typify_tree(node.children[1]) # node.children[0] is a decorator.
#   elif node.type == 'async_stmt':
#     self.typify_tree(node.children[1]) # node.children[0] is 'async'.
#   elif node.type == 'if_stmt':
#     self.handle_if_stmt(node)
#   elif node.type == 'expr_stmt':
#     self.handle_expr_stmt(node)
#   elif node.type == 'for_stmt':
#     self.handle_for_stmt(node)
#   elif node.type == 'while_stmt':
#     self.handle_while_stmt(node)
#   elif node.type == 'try_stmt':
#     self.handle_try_stmt(node)
#   elif node.type == 'with_stmt':
#     self.handle_with_stmt(node)
#   else:
#     assert False, node_info(node)
