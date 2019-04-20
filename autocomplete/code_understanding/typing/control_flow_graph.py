# from __future__ import annotations
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
import sys
import traceback

import attr

import parso
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (
    ExpressionCfgNode, FromImportCfgNode, FuncCfgNode, GroupCfgNode, IfCfgNode,
    ImportCfgNode, KlassCfgNode, NoOpCfgNode, ReturnCfgNode)
from autocomplete.code_understanding.typing.errors import (
    ParsingError, assert_unexpected_parso)
from autocomplete.code_understanding.typing.frame import Frame
from autocomplete.code_understanding.typing.utils import (
    create_expression_node_tuples_from_if_stmt, expression_from_node, node_info,
    parameters_from_parameters, statement_node_from_expr_stmt)
from autocomplete.nsn_logging import debug, error, info, warning


def run_graph(graph, frame=None):
  # TODO: Create proper.
  if not frame:
    frame = Frame()
  graph.process(frame)
  return frame


def condense_graph(graph):
  if not hasattr(graph, 'children'):
    return graph

  children = [condense_graph(child) for child in graph.children]
  children = list(filter(lambda x: not isinstance(x, NoOpCfgNode), children))
  if children:
    return NoOpCfgNode(graph.parso_node)
  elif len(children) == 1:
    return children[0]
  return GroupCfgNode(children, parso_node=graph.parso_node)


# def handle_error(e, node):
# traceback.print_tb(e.tb)
# raise e


class TypingException(Exception):
  ...


@attr.s
class ControlFlowGraphBuilder:
  module_loader = attr.ib()

  def create_cfg_node(self, node):
    '''Create handles all nodes which should create their own CfgNode - i.e.
    nodes that contain a complete statement/definition or control flow.'''
    try:
      if hasattr(self, f'create_cfg_node_for_{node.type}'):
        return getattr(self, f'create_cfg_node_for_{node.type}')(node)
      debug(f'Unhandled type: {node.type}')
    except (
        NotImplementedError,
        ParsingError  # AttributeError, ValueError
    ) as e:  # For reasons beyond me, 'as e' causes this not to be caught...
      # handle_error(e, node)
      error(f'Caught {type(e)}: {e} while creating: {node.get_code()}')
    # except Exception as e:
    #   raise TypingException(e) from e # Wrap other exceptions in this so we can be sure they don't get caught later.
    #   handle_error(e, node)
    # except:
    #   pass
    return NoOpCfgNode(node)
    # except NotImplementedError as e:
    #   handle_error(e, node)

  def create_cfg_node_for_error_node(self, node):
    debug(f'Error node when processing: {node.get_code()}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_single_input(self, node):
    return GroupCfgNode(
        [self.create_cfg_node(child) for child in node.children],
        parso_node=node)

  def create_cfg_node_for_file_input(self, node):
    return GroupCfgNode(
        [self.create_cfg_node(child) for child in node.children],
        parso_node=node)

  def create_cfg_node_for_eval_input(self, node):
    return GroupCfgNode(
        [self.create_cfg_node(child) for child in node.children],
        parso_node=node)

  def create_cfg_node_for_stmt(self, node):
    return GroupCfgNode(
        [self.create_cfg_node(child) for child in node.children],
        parso_node=node)

  def create_cfg_node_for_simple_stmt(self, node):
    return GroupCfgNode(
        [self.create_cfg_node(child) for child in node.children],
        parso_node=node)

  def create_cfg_node_for_small_stmt(self, node):
    return GroupCfgNode(
        [self.create_cfg_node(child) for child in node.children],
        parso_node=node)

  def create_cfg_node_for_suite(self, node):
    return GroupCfgNode(
        [self.create_cfg_node(child) for child in node.children],
        parso_node=node)

  # Noop nodes for our purposes.
  def create_cfg_node_for_del_stmt(self, node):
    return NoOpCfgNode(node)

  def create_cfg_node_for_keyword(self, node):
    assert_unexpected_parso(node.value == 'pass', node_info)
    return NoOpCfgNode(node)

  def create_cfg_node_for_string(self, node):
    # TODO: Documentation?
    return NoOpCfgNode(node)

  def create_cfg_node_for_pass(self, node):
    return NoOpCfgNode(node)

  def create_cfg_node_for_newline(self, node):
    return NoOpCfgNode(node)

  def create_cfg_node_for_endmarker(self, node):
    return NoOpCfgNode(node)

  def create_cfg_node_for_name(self, node):
    return NoOpCfgNode(node)

  def create_cfg_node_for_decorated(self, node):
    # TODO: Handle first child decorator or decorators.
    assert_unexpected_parso(len(node.children) == 2, node_info(node))
    return self.create_cfg_node(node.children[1])

  # def create_cfg_node_for_decorator(self, node): debug(f'Skipping {node.type}')
  # def create_cfg_node_for_decorators(self, node): debug(f'Skipping {node.type}')

  # Parso doesn't handle these grammar nodes in the expectezd way:
  # async_func's are treated as async_stmt with a funcdef inside.
  # def create_cfg_node_for_async_funcdef(self, node): debug(f'Skipping {node.type}')

  # augassign is treated as a regular assignment with a special operator (e.g. +=)
  # def create_cfg_node_for_augassign(self, node): debug(f'Skipping {node.type}')

  def create_cfg_node_for_if_stmt(self, node):
    return IfCfgNode(
        create_expression_node_tuples_from_if_stmt(self, node), node)

  def create_cfg_node_for_funcdef(self, node):
    # Children are: def name params : suite
    name = node.children[1].value
    parameters = parameters_from_parameters(node.children[2])
    suite = self.create_cfg_node(node.children[-1])
    return FuncCfgNode(name, parameters, suite, parso_node=node)

  def create_cfg_node_for_expr_stmt(self, node):
    return statement_node_from_expr_stmt(node)
    # debug(f'Creating AssignmentStmtCfgNode for {node}')
    # return AssignmentStmtCfgNode(statement, node)

  def create_cfg_node_for_atom_expr(self, node):
    expression = expression_from_node(node)
    return ExpressionCfgNode(expression, parso_node=node)

  def create_cfg_node_for_return_stmt(self, node):
    # First child is 'return', second is result.
    assert_unexpected_parso(len(node.children) == 2, node_info(node))
    return ReturnCfgNode(
        expression_from_node(node.children[1]), parso_node=node)

  def create_cfg_node_for_flow_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_break_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_continue_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_yield_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_raise_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_import_stmt(self, node):
    assert_unexpected_parso(False, "Not used.")
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_import_name(self, node):
    # import_name: 'import' dotted_as_names
    # dotted_as_names: dotted_as_name (',' dotted_as_name)*
    # dotted_as_name: dotted_name ['as' NAME]
    # dotted_name: NAME ('.' NAME)*
    child = node.children[1]  # 0 is 'import'
    if child.type == 'name':
      return ImportCfgNode(
          child.value, parso_node=node, module_loader=self.module_loader)
    if child.type == 'dotted_as_name':
      path, as_name = self.path_and_name_from_dotted_as_name(child)
      return ImportCfgNode(
          path,
          as_name=as_name,
          parso_node=node,
          module_loader=self.module_loader)

    assert_unexpected_parso(child.type == 'dotted_as_names', node_info(child))
    # Some combination of things.
    import_nodes = []
    out = GroupCfgNode(import_nodes, parso_node=node)
    dotted_as_names = child
    for child in dotted_as_names.children:
      if child.type == 'name':
        import_nodes.append(
            ImportCfgNode(
                child.value,
                as_name=None,
                parso_node=node,
                module_loader=self.module_loader))
      elif child.type == 'operator':
        assert_unexpected_parso(child.value == ',', node_info(child))
      else:
        assert_unexpected_parso(child.type == 'dotted_as_name',
                                node_info(child))
        path, as_name = self.path_and_name_from_dotted_as_name(child)
        import_nodes.append(
            ImportCfgNode(
                path,
                as_name=as_name,
                parso_node=node,
                module_loader=self.module_loader))
    return out

  def path_and_name_from_dotted_as_name(self, node):
    assert_unexpected_parso(node.type == 'dotted_as_name', node_info(node))
    if node.children[0].type == 'name':
      path = node.children[0].value
    else:
      dotted_name = node.children[0]
      assert_unexpected_parso(dotted_name.type == 'dotted_name',
                              node_info(dotted_name))
      path = ''.join([child.value for child in dotted_name.children])
    if len(node.children) == 1:  # import x
      return path, None
    # import a as b
    assert_unexpected_parso(len(node.children) == 3, node_info(node))
    return path, node.children[-1].value

  def create_cfg_node_for_import_from(self, node):
    # import_from: ('from' (('.' | '...')* dotted_name | ('.' | '...')+)
    #              'import' ('*' | '(' import_as_names ')' | import_as_names))
    # import_as_name: NAME ['as' NAME]
    # from is first child
    debug(node.get_code())
    node_index = 1
    # First node after import might be '.' or '...' operators.

    path_node = node.children[node_index]
    path = ''
    if path_node.type == 'operator':  # Example from . import y
      path = path_node.value
      node_index += 1
      path_node = node.children[node_index]

    if path_node.type == 'name':  # Example from a import y
      path += path_node.value
      node_index += 2
    elif path_node.type == 'dotted_name':  # Example from b.a import y
      path += ''.join([child.value for child in path_node.children])
      node_index += 2
    else:  # Example from . import y
      assert_unexpected_parso(
          path_node.type == 'keyword' and path_node.value == 'import',
          node_info(node))
      node_index += 1

    # import is next node, so we do +2 instead of +1.
    next_node = node.children[node_index]

    # Example: import os as whatever
    if next_node.type == 'operator' and next_node.value == '(':  # from x import (y)
      next_node = node.children[node_index + 1]
    # Example: from a import *
    if next_node.type == 'operator' and next_node.value == '*':
      return FromImportCfgNode(
          path,
          from_import_name='*',
          as_name=None,
          parso_node=node,
          module_loader=self.module_loader)

    # Example: from a.b import c
    if next_node.type == 'name':
      return FromImportCfgNode(
          path,
          next_node.value,
          parso_node=node,
          module_loader=self.module_loader)

    # Example: from x.y.z import r as s
    if next_node.type == 'import_as_name':
      assert_unexpected_parso(
          len(next_node.children) == 3, node_info(next_node))
      return FromImportCfgNode(
          path,
          from_import_name=next_node.children[0].value,
          as_name=next_node.children[-1].value,
          parso_node=node,
          module_loader=self.module_loader)

    # Example: from a import b, c as d
    assert_unexpected_parso(next_node.type == 'import_as_names',
                            node_info(next_node))
    from_import_nodes = []
    out = GroupCfgNode(from_import_nodes, parso_node=node)
    for child in next_node.children:
      if child.type == 'name':
        from_import_nodes.append(
            FromImportCfgNode(
                path,
                from_import_name=child.value,
                parso_node=node,
                module_loader=self.module_loader))
      elif child.type == 'operator':
        assert_unexpected_parso(child.value == ',', node_info(node))
      else:
        assert_unexpected_parso(child.type == 'import_as_name',
                                node_info(child))
        assert_unexpected_parso(len(child.children) == 3, node_info(child))
        from_import_nodes.append(
            FromImportCfgNode(
                path,
                from_import_name=child.children[0].value,
                as_name=child.children[-1].value,
                parso_node=node,
                module_loader=self.module_loader))
    return out

  def create_cfg_node_for_global_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_nonlocal_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_assert_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_compound_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_async_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_while_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_for_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_try_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_except_clause(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_with_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_with_item(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  def create_cfg_node_for_classdef(self, node):
    name = node.children[1].value
    suite = self.create_cfg_node(node.children[-1])
    return KlassCfgNode(name, suite, parso_node=node)

  # def process_parameters(self, node): debug(f'Skipping {node.type}')
  # def process_typedargslist(self, node): debug(f'Skipping {node.type}')
  # def process_tfpdef(self, node): debug(f'Skipping {node.type}')
  # def process_varargslist(self, node): debug(f'Skipping {node.type}')
  # def process_vfpdef(self, node): debug(f'Skipping {node.type}')
  # def process_annassign(self, node): debug(f'Skipping {node.type}')
  # def process_testlist_star_expr(self, node): debug(f'Skipping {node.type}')
  # def process_import_as_name(self, node): debug(f'Skipping {node.type}')
  # def process_dotted_as_name(self, node): debug(f'Skipping {node.type}')
  # def process_import_as_names(self, node): debug(f'Skipping {node.type}')
  # def process_dotted_as_names(self, node): debug(f'Skipping {node.type}')
  # def process_dotted_name(self, node): debug(f'Skipping {node.type}')

  # def process_test(self, node): debug(f'Skipping {node.type}')
  # def process_test_nocond(self, node): debug(f'Skipping {node.type}')
  # def process_lambdef(self, node): debug(f'Skipping {node.type}')
  # def process_lambdef_nocond(self, node): debug(f'Skipping {node.type}')
  # def process_or_test(self, node): debug(f'Skipping {node.type}')
  # def process_and_test(self, node): debug(f'Skipping {node.type}')
  # def process_not_test(self, node): debug(f'Skipping {node.type}')
  # def process_comparison(self, node): debug(f'Skipping {node.type}')
  # def process_comp_op(self, node): debug(f'Skipping {node.type}')
  # def process_star_expr(self, node): debug(f'Skipping {node.type}')
  # def process_expr(self, node): debug(f'Skipping {node.type}')
  # def process_xor_expr(self, node): debug(f'Skipping {node.type}')
  # def process_and_expr(self, node): debug(f'Skipping {node.type}')
  # def process_shift_expr(self, node): debug(f'Skipping {node.type}')
  # def process_arith_expr(self, node): debug(f'Skipping {node.type}')
  # def process_term(self, node): debug(f'Skipping {node.type}')
  # def process_factor(self, node): debug(f'Skipping {node.type}')
  # def process_power(self, node): debug(f'Skipping {node.type}')

  # def process_atom(self, node): debug(f'Skipping {node.type}')
  # def process_testlist_comp(self, node): debug(f'Skipping {node.type}')
  # def process_trailer(self, node): debug(f'Skipping {node.type}')
  # def process_subscriptlist(self, node): debug(f'Skipping {node.type}')
  # def process_subscript(self, node): debug(f'Skipping {node.type}')
  # def process_sliceop(self, node): debug(f'Skipping {node.type}')
  # def process_exprlist(self, node): debug(f'Skipping {node.type}')
  # def process_testlist(self, node): debug(f'Skipping {node.type}')
  # def process_dictorsetmaker(self, node): debug(f'Skipping {node.type}')

  # def process_arglist(self, node): debug(f'Skipping {node.type}')
  # def process_argument(self, node): debug(f'Skipping {node.type}')
  # def process_comp_iter(self, node): debug(f'Skipping {node.type}')
  # def process_sync_comp_for(self, node): debug(f'Skipping {node.type}')
  # def process_comp_for(self, node): debug(f'Skipping {node.type}')
  # def process_comp_if(self, node): debug(f'Skipping {node.type}')
  # def process_encoding_decl(self, node): debug(f'Skipping {node.type}')
  # def process_yield_expr(self, node): debug(f'Skipping {node.type}')
  # def process_yield_arg(self, node): debug(f'Skipping {node.type}')


# if __name__ == '__main__':
#   basic_node = parso.parse('a=1')
#   ControlFlowGraphBuilder().create_cfg_node(basic_node)
