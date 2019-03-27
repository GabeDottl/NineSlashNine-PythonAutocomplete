# from __future__ import annotations
from functools import wraps

import attr

from autocomplete.code_understanding.typing.classes import *
from autocomplete.code_understanding.typing.utils import *

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

def run_graph(graph, frame=None):
  # TODO: Create proper.
  if not frame:
    frame = Frame(globals={}, locals={})
  graph.process(frame, None)
  return frame

def condense_graph(graph):
  if not hasattr(graph, 'children'):
    return graph

  children = [condense_graph(child) for child in graph.children]
  children = list(filter(lambda x: not isinstance(x, NoOpCfgNode), children))
  if len(children) == 0:
    return NoOpCfgNode()
  elif len(children) == 1:
    return children[0]
  else:
    return GroupCFGNode(children)


class ControlFlowGraph:
  def create_cfg_node(self, node):
    '''Create handles all nodes which should create their own CFGNode - i.e.
    nodes that contain a complete statement/definition or control flow.'''
    return getattr(self, f'create_cfg_node_for_{node.type}')(node)


  def create_cfg_node_for_single_input(self, node): return GroupCFGNode([self.create_cfg_node(child) for child in node.children])
  def create_cfg_node_for_file_input(self, node): return GroupCFGNode([self.create_cfg_node(child) for child in node.children])
  def create_cfg_node_for_eval_input(self, node): return GroupCFGNode([self.create_cfg_node(child) for child in node.children])
  def create_cfg_node_for_stmt(self, node): return GroupCFGNode([self.create_cfg_node(child) for child in node.children])
  def create_cfg_node_for_simple_stmt(self, node): return GroupCFGNode([self.create_cfg_node(child) for child in node.children])
  def create_cfg_node_for_small_stmt(self, node): return GroupCFGNode([self.create_cfg_node(child) for child in node.children])
  def create_cfg_node_for_suite(self, node): return GroupCFGNode([self.create_cfg_node(child) for child in node.children])

  # Noop nodes for our purposes.
  def create_cfg_node_for_del_stmt(self, node): return NoOpCfgNode()
  def create_cfg_node_for_pass(self, node): return NoOpCfgNode()
  def create_cfg_node_for_newline(self, node): return NoOpCfgNode()
  def create_cfg_node_for_endmarker(self, node): return NoOpCfgNode()

  def create_cfg_node_for_decorated(self, node):
    # TODO: Handle first child decorator or decorators.
    assert len(node.children) == 1, node_info(node)
    return self.create_cfg_node(node.children[1])

  # def create_cfg_node_for_decorator(self, node): print(f'Skipping {node.type}')
  # def create_cfg_node_for_decorators(self, node): print(f'Skipping {node.type}')

  # Parso doesn't handle these grammar nodes in the expected way:
  # async_func's are treated as async_stmt with a funcdef inside.
  # def create_cfg_node_for_async_funcdef(self, node): print(f'Skipping {node.type}')

  # augassign is treated as a regular assignment with a special operator (e.g. +=)
  # def create_cfg_node_for_augassign(self, node): print(f'Skipping {node.type}')

  def create_cfg_node_for_if_stmt(self, node):
    

  def create_cfg_node_for_funcdef(self, node):
    children = [self.create_cfg_node(child) for child in node.children]
    return FuncCFGNode(children)

  def create_cfg_node_for_expr_stmt(self, node):
    statement = statement_from_expr_stmt(node)
    print(f'Creating StmtCFGNode for {node.get_code()}')
    return StmtCFGNode(statement, node.get_code())

  def create_cfg_node_for_flow_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_break_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_continue_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_return_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_yield_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_raise_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_import_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_import_name(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_import_from(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_global_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_nonlocal_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_assert_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_compound_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_async_stmt(self, node): print(f'Skipping {node.type}')

  def create_cfg_node_for_while_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_for_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_try_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_except_clause(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_with_stmt(self, node): print(f'Skipping {node.type}')
  def create_cfg_node_for_with_item(self, node): print(f'Skipping {node.type}')


  def create_cfg_node_for_classdef(self, node): print(f'Skipping {node.type}')
  # def process_parameters(self, node): print(f'Skipping {node.type}')
  # def process_typedargslist(self, node): print(f'Skipping {node.type}')
  # def process_tfpdef(self, node): print(f'Skipping {node.type}')
  # def process_varargslist(self, node): print(f'Skipping {node.type}')
  # def process_vfpdef(self, node): print(f'Skipping {node.type}')
  # def process_annassign(self, node): print(f'Skipping {node.type}')
  # def process_testlist_star_expr(self, node): print(f'Skipping {node.type}')
  # def process_import_as_name(self, node): print(f'Skipping {node.type}')
  # def process_dotted_as_name(self, node): print(f'Skipping {node.type}')
  # def process_import_as_names(self, node): print(f'Skipping {node.type}')
  # def process_dotted_as_names(self, node): print(f'Skipping {node.type}')
  # def process_dotted_name(self, node): print(f'Skipping {node.type}')

  # def process_test(self, node): print(f'Skipping {node.type}')
  # def process_test_nocond(self, node): print(f'Skipping {node.type}')
  # def process_lambdef(self, node): print(f'Skipping {node.type}')
  # def process_lambdef_nocond(self, node): print(f'Skipping {node.type}')
  # def process_or_test(self, node): print(f'Skipping {node.type}')
  # def process_and_test(self, node): print(f'Skipping {node.type}')
  # def process_not_test(self, node): print(f'Skipping {node.type}')
  # def process_comparison(self, node): print(f'Skipping {node.type}')
  # def process_comp_op(self, node): print(f'Skipping {node.type}')
  # def process_star_expr(self, node): print(f'Skipping {node.type}')
  # def process_expr(self, node): print(f'Skipping {node.type}')
  # def process_xor_expr(self, node): print(f'Skipping {node.type}')
  # def process_and_expr(self, node): print(f'Skipping {node.type}')
  # def process_shift_expr(self, node): print(f'Skipping {node.type}')
  # def process_arith_expr(self, node): print(f'Skipping {node.type}')
  # def process_term(self, node): print(f'Skipping {node.type}')
  # def process_factor(self, node): print(f'Skipping {node.type}')
  # def process_power(self, node): print(f'Skipping {node.type}')
  # def process_atom_expr(self, node): print(f'Skipping {node.type}')
  # def process_atom(self, node): print(f'Skipping {node.type}')
  # def process_testlist_comp(self, node): print(f'Skipping {node.type}')
  # def process_trailer(self, node): print(f'Skipping {node.type}')
  # def process_subscriptlist(self, node): print(f'Skipping {node.type}')
  # def process_subscript(self, node): print(f'Skipping {node.type}')
  # def process_sliceop(self, node): print(f'Skipping {node.type}')
  # def process_exprlist(self, node): print(f'Skipping {node.type}')
  # def process_testlist(self, node): print(f'Skipping {node.type}')
  # def process_dictorsetmaker(self, node): print(f'Skipping {node.type}')

  # def process_arglist(self, node): print(f'Skipping {node.type}')
  # def process_argument(self, node): print(f'Skipping {node.type}')
  # def process_comp_iter(self, node): print(f'Skipping {node.type}')
  # def process_sync_comp_for(self, node): print(f'Skipping {node.type}')
  # def process_comp_for(self, node): print(f'Skipping {node.type}')
  # def process_comp_if(self, node): print(f'Skipping {node.type}')
  # def process_encoding_decl(self, node): print(f'Skipping {node.type}')
  # def process_yield_expr(self, node): print(f'Skipping {node.type}')
  # def process_yield_arg(self, node): print(f'Skipping {node.type}')
