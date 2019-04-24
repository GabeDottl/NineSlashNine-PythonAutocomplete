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
from functools import wraps
from typing import List, Tuple

import attr
import parso

from autocomplete.code_understanding.typing.control_flow_graph_nodes import (
    AssignmentStmtCfgNode, CfgNode, ExceptCfgNode, ExpressionCfgNode,
    ForCfgNode, FromImportCfgNode, FuncCfgNode, GroupCfgNode, IfCfgNode,
    ImportCfgNode, KlassCfgNode, NoOpCfgNode, ReturnCfgNode, TryCfgNode,
    WhileCfgNode, WithCfgNode)
from autocomplete.code_understanding.typing.errors import (
    ParsingError, assert_unexpected_parso)
from autocomplete.code_understanding.typing.expressions import (
    Expression, LiteralExpression, UnknownExpression, VariableExpression)
from autocomplete.code_understanding.typing.frame import Frame
from autocomplete.code_understanding.typing.parsing_utils import (
    _assert_returns_type, expression_from_node, node_info,
    parameters_from_parameters, statement_node_from_expr_stmt,
    variables_from_node)
from autocomplete.nsn_logging import debug, error, info, warning


def condense_graph(graph):
  if not isinstance(graph, GroupCfgNode):
    return graph

  children = [condense_graph(child) for child in graph.children]
  children = list(filter(lambda x: not isinstance(x, NoOpCfgNode), children))
  if not children:
    return NoOpCfgNode(graph.parso_node)
  elif len(children) == 1:
    return children[0]
  return GroupCfgNode(children, parso_node=graph.parso_node)


class TypingException(Exception):
  ...


@attr.s
class ControlFlowGraphBuilder:
  module_loader = attr.ib()
  _module: 'Module' = attr.ib()
  root: GroupCfgNode = attr.ib(factory=GroupCfgNode)
  _current_containing_func = None

  def graph_from_parso_node(self, parso_node):
    self.root.children.append(self._create_cfg_node(parso_node))
    return self.root

  @_assert_returns_type(CfgNode)
  def _create_cfg_node(self, node):
    '''Create handles all nodes which should create their own CfgNode - i.e.
    nodes that contain a complete statement/definition or control flow.
    '''
    try:
      if hasattr(self, f'_create_cfg_node_for_{node.type}'):
        return getattr(self, f'_create_cfg_node_for_{node.type}')(node)
      debug(f'Unhandled type: {node.type}')
    except (
        NotImplementedError, ParsingError
    ) as e:  # For reasons beyond me, 'as e' causes this not to be caught...
      # handle_error(e, node)
      error(f'Caught {type(e)}: {e} while creating: {node.get_code()}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_error_node(self, node):
    debug(f'Error node when processing: {node.get_code()}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_single_input(self, node):
    return GroupCfgNode(
        [self._create_cfg_node(child) for child in node.children],
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_file_input(self, node):
    return GroupCfgNode(
        [self._create_cfg_node(child) for child in node.children],
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_eval_input(self, node):
    return GroupCfgNode(
        [self._create_cfg_node(child) for child in node.children],
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_stmt(self, node):
    return GroupCfgNode(
        [self._create_cfg_node(child) for child in node.children],
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_simple_stmt(self, node):
    return GroupCfgNode(
        [self._create_cfg_node(child) for child in node.children],
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_small_stmt(self, node):
    return GroupCfgNode(
        [self._create_cfg_node(child) for child in node.children],
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_suite(self, node):
    return GroupCfgNode(
        [self._create_cfg_node(child) for child in node.children],
        parso_node=node)

  # Noop nodes for our purposes.
  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_del_stmt(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_keyword(self, node):
    if node.value == 'pass' or node.value == 'break' or node.value == 'continue' or node.value == 'yield':
      return NoOpCfgNode(node)
    if node.value == 'return':
      return ReturnCfgNode(LiteralExpression(None), parso_node=node)
    assert_unexpected_parso(False, node_info)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_string(self, node):
    # TODO: Documentation?
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_pass(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_newline(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_endmarker(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_name(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_decorated(self, node):
    # TODO: Handle first child decorator or decorators.
    assert_unexpected_parso(len(node.children) == 2, node_info(node))
    return self._create_cfg_node(node.children[1])

  # @_assert_returns_type(CfgNode)
  # def _create_cfg_node_for_decorator(self, node): debug(f'Skipping {node.type}')
  # @_assert_returns_type(CfgNode)
  # def _create_cfg_node_for_decorators(self, node): debug(f'Skipping {node.type}')

  # Parso doesn't handle these grammar nodes in the expectezd way:
  # async_func's are treated as async_stmt with a funcdef inside.
  # @_assert_returns_type(CfgNode)
  # def _create_cfg_node_for_async_funcdef(self, node): debug(f'Skipping {node.type}')

  # augassign is treated as a regular assignment with a special operator (e.g. +=)
  # @_assert_returns_type(CfgNode)
  # def _create_cfg_node_for_augassign(self, node): debug(f'Skipping {node.type}')

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_if_stmt(self, node):
    return IfCfgNode(
        self.create_expression_node_tuples_from_if_stmt(node), node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_funcdef(self, node):
    # Children are: def name params : suite
    name = node.children[1].value
    parameters = parameters_from_parameters(node.children[2])
    old_containing_func = self._current_containing_func
    out = FuncCfgNode(
        name,
        parameters,
        suite=None,
        module=self._module,
        containing_func_node=old_containing_func,
        parso_node=node)
    self._current_containing_func = out
    suite = self._create_cfg_node(node.children[-1])
    out.suite = suite
    self._current_containing_func = old_containing_func
    return out

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_expr_stmt(self, node):
    return statement_node_from_expr_stmt(node)
    # debug(f'Creating AssignmentStmtCfgNode for {node}')
    # return AssignmentStmtCfgNode(statement, node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_atom_expr(self, node):
    expression = expression_from_node(node)
    return ExpressionCfgNode(expression, parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_return_stmt(self, node):
    # First child is 'return', second is result.
    assert_unexpected_parso(len(node.children) == 2, node_info(node))
    return ReturnCfgNode(
        expression_from_node(node.children[1]), parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_flow_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_break_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_continue_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_yield_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_raise_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_import_stmt(self, node):
    assert_unexpected_parso(False, "Not used.")
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_import_name(self, node):
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

    # Example: import a.b
    if child.type == 'dotted_name':
      dotted_name = child
      path = ''.join([child.value for child in dotted_name.children])
      return ImportCfgNode(
          path, parso_node=node, module_loader=self.module_loader)

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

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_import_from(self, node):
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

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_global_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_nonlocal_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_assert_stmt(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_compound_stmt(self, node):
    assert False
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_async_stmt(self, node):
    debug(f'Ignoring async in {node.type}')
    return self._create_cfg_node(node.children[1])

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_while_stmt(self, node):
    assert len(node.children) == 4 or len(node.children) == 7, node_info(node)
    conditional_expression = expression_from_node(node.children[1])
    suite = self._create_cfg_node(node.children[3])
    else_suite = self._create_cfg_node(node.children[-1]) if len(
        node.children) == 7 else NoOpCfgNode(node.children[-1])

    return WhileCfgNode(
        conditional_expression, suite, else_suite, parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_for_stmt(self, node):
    # Example for loop_variables in loop_expression: suite
    loop_variables = variables_from_node(node.children[1])
    assert not isinstance(loop_variables, UnknownExpression)
    loop_expression = expression_from_node(node.children[3])
    suite = self._create_cfg_node(node.children[-1])
    return ForCfgNode(loop_variables, loop_expression, suite, parso_node=node)

  @_assert_returns_type(TryCfgNode)
  def _create_cfg_node_for_try_stmt(self, node):
    try_suite = self._create_cfg_node(node.children[2])

    except_nodes = []
    for i in range(3, len(node.children), 3):
      keyword = node.children[i]
      suite_node = self._create_cfg_node(node.children[i + 2])
      if keyword.type == 'keyword':
        if keyword.value == 'finally' or keyword.value == 'else':
          break
        assert keyword.value == 'except'
        except_nodes.append(ExceptCfgNode([], None, suite_node))
      else:
        assert keyword.type == 'except_clause'
        except_clause = keyword
        exceptions = variables_from_node(except_clause.children[1])
        if len(except_clause.children) == 4:
          exception_variable = VariableExpression(except_clause.children[-1])
        else:
          exception_variable = None
        except_nodes.append(
            ExceptCfgNode(exceptions, exception_variable, suite_node))
    else_suite = NoOpCfgNode(node)
    finally_suite = NoOpCfgNode(node)
    if keyword.type == 'keyword' and keyword.value != 'except':
      if keyword.value == 'else':
        else_suite = suite_node
        i += 3
        if i < len(node.children):
          keyword = node.children[i]
          assert keyword.type == 'keyword' and keyword.value == 'finally'
          finally_suite = self._create_cfg_node(node.children[i + 2])

    # if node.children[-3].type == 'keyword' and node.children[
    #     -3].value == 'finally':
    #   finally_suite = self._create_cfg_node(node.children[-1])
    #     # Example: try: suite finally: finally_suite
    # if len(node.children) == 6 and node.children[
    #     4].type == 'keyword' and node.children[4].value == 'finally':
    #   finally_suite = self._create_cfg_node(node.children[-1])
    return TryCfgNode(
        try_suite,
        except_nodes,
        else_suite=else_suite,
        finally_suite=finally_suite)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_except_clause(self, node):
    assert False

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_with_stmt(self, node):
    with_item = node.children[1]
    as_name = None
    if with_item.type == 'with_item':
      with_item_expression = expression_from_node(with_item.children[0])
      if len(with_item.children) == 3:
        as_name = expression_from_node(with_item.children[-1])
      else:
        assert len(with_item.children) == 1, node
    else:
      with_item_expression = expression_from_node(with_item)

    suite = self._create_cfg_node(node.children[-1])
    return WithCfgNode(with_item_expression, as_name, suite, parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_with_item(self, node):
    debug(f'Skipping {node.type}')
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_classdef(self, node):
    name = node.children[1].value
    suite = self._create_cfg_node(node.children[-1])
    return KlassCfgNode(name, suite, parso_node=node)

  @_assert_returns_type(List)
  def create_expression_node_tuples_from_if_stmt(
      self, node) -> List[Tuple[Expression, CfgNode]]:
    expression_node_tuples = []
    iterator = iter(node.children)
    for child in iterator:
      try:
        # Few cases:
        # 1) {if/elif} {conditional} : {suite}
        # 2) else : {suite}
        assert_unexpected_parso(child.type == 'keyword',
                                (node_info(node), node_info(child)))
        conditional_or_op = next(
            iterator)  # Conditional expression or an operator.
        if conditional_or_op.type == 'operator':
          assert_unexpected_parso(
              child.value == 'else' and conditional_or_op.value == ':',
              (conditional_or_op, child))
          expression = LiteralExpression(True)
        else:
          expression = expression_from_node(conditional_or_op)
          assert_unexpected_parso(expression, node_info(child))
          n = next(iterator)  # Skip past the operator
          assert_unexpected_parso(n.type == 'operator', node_info(n))
        content = next(iterator)
        cfg_node = self._create_cfg_node(content)

        expression_node_tuples.append((expression, cfg_node))
      except StopIteration:
        pass
    return expression_node_tuples
