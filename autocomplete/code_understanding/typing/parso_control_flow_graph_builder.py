
import itertools
import sys
from functools import wraps
from symbol import dictorsetmaker
from typing import Dict, List, Tuple, Union

from autocomplete.code_understanding.typing.control_flow_graph_nodes import (
    AssignmentStmtCfgNode, CfgNode, GroupCfgNode)
from autocomplete.code_understanding.typing.errors import (
    ParsingError, assert_unexpected_parso)
from autocomplete.code_understanding.typing.expressions import (
    AndOrExpression, AttributeExpression, CallExpression, ComparisonExpression,
    DictExpression, Expression, FactorExpression, ForComprehension,
    ForComprehensionExpression, IfElseExpression, ItemListExpression,
    KeyValueAssignment, KeyValueForComp, ListExpression, LiteralExpression,
    MathExpression, NotExpression, SetExpression, StarredExpression,
    SubscriptExpression, TupleExpression, UnknownExpression, Variable,
    VariableExpression)
from autocomplete.code_understanding.typing.language_objects import (
    Parameter, ParameterType)
from autocomplete.nsn_logging import debug, error, info, warning
# TODO: Clean these....
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
from autocomplete.code_understanding.typing.pobjects import NONE_POBJECT
from autocomplete.code_understanding.typing.expressions import (
    AnonymousExpression, Expression, LiteralExpression, UnknownExpression,
    VariableExpression)
from autocomplete.code_understanding.typing.frame import Frame
from autocomplete.nsn_logging import debug, error, info, warning


def _assert_returns_type(type_):

  def wrapper(func):

    @wraps(func)
    def inner_wrapper(*args, **kwargs):
      cfg_node = func(*args, **kwargs)
      assert isinstance(cfg_node, type_)
      return cfg_node

    return inner_wrapper

  return wrapper



EXPRESSION_NODES = {
    'testlist_star_expr', 'comparison', 'star_expr', 'expr', 'xor_expr',
    'arith_expr', 'and_expr', 'and_test', 'or_test', 'not_test', 'comparison',
    'comp_op', 'shift_expr', 'arith_expr', 'term', 'factor', 'power',
    'atom_expr', 'atom', 'starexpr', 'lambda', 'lambdef_nocond', 'exprlist',
    'testlist_comp', 'dictorsetmaker', 'name', 'number', 'string', 'strings'
}


@attr.s
class ParsoControlFlowGraphBuilder:
  module_loader = attr.ib()
  _module: 'Module' = attr.ib()
  root: GroupCfgNode = attr.ib(factory=GroupCfgNode)
  _current_containing_func = None

  def graph_from_source(self, source):
    parso_node = parso.parse(source)
    self.root.children.append(self._create_cfg_node(parso_node))
    return self.root

  @_assert_returns_type(CfgNode)
  def _create_cfg_node(self, node):
    '''Create handles all nodes which should create their own CfgNode - i.e.
    nodes that contain a complete statement/definition or control flow.
    '''
    try:
      # The are nodes which represent expressions - if they're encountered directly in the process
      # of creating CfgNodes, we simply want to wrap them in an ExpressionCfgNode.
      if node.type in EXPRESSION_NODES:
        return ExpressionCfgNode(expression_from_node(node), node)
      if hasattr(self, f'_create_cfg_node_for_{node.type}'):
        return getattr(self, f'_create_cfg_node_for_{node.type}')(node)
      error(f'Unhandled type: {node.type}')
      raise ParsingError(f'Unhandled type: {node.type}')
    except ParsingError as e:
      import traceback
      traceback.print_tb(e.__traceback__)
      error(f'Caught {type(e)}: {e} while creating: {node.get_code()}')
      raise e
    except NotImplementedError as e:
      # import traceback
      # traceback.print_tb(e.__traceback__)
      # warning(f'{type(e)}: {e}')
      pass

    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_error_leaf(self, node):
    info(f'Error leaf when processing: "{node.get_code()}"')
    # assert False
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_error_node(self, node):
    info(f'Error node when processing: "{node.get_code()}"')
    # assert False
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_single_input(self, node):
    return GroupCfgNode(
        list(
            filter(lambda x: not isinstance(x, NoOpCfgNode),
                   [self._create_cfg_node(child) for child in node.children])),
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_file_input(self, node):
    return GroupCfgNode(
        list(
            filter(lambda x: not isinstance(x, NoOpCfgNode),
                   [self._create_cfg_node(child) for child in node.children])),
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_eval_input(self, node):
    return GroupCfgNode(
        list(
            filter(lambda x: not isinstance(x, NoOpCfgNode),
                   [self._create_cfg_node(child) for child in node.children])),
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_stmt(self, node):
    return GroupCfgNode(
        list(
            filter(lambda x: not isinstance(x, NoOpCfgNode),
                   [self._create_cfg_node(child) for child in node.children])),
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_simple_stmt(self, node):
    return GroupCfgNode(
        list(
            filter(lambda x: not isinstance(x, NoOpCfgNode),
                   [self._create_cfg_node(child) for child in node.children])),
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_small_stmt(self, node):
    return GroupCfgNode(
        list(
            filter(lambda x: not isinstance(x, NoOpCfgNode),
                   [self._create_cfg_node(child) for child in node.children])),
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_suite(self, node):
    return GroupCfgNode(
        list(
            filter(lambda x: not isinstance(x, NoOpCfgNode),
                   [self._create_cfg_node(child) for child in node.children])),
        parso_node=node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_operator(self, node):
    assert node.value == '...' or node.value == ';'
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_keyword(self, node):
    if node.value == 'return':
      return ReturnCfgNode(LiteralExpression(None), parso_node=node)
    # if node.value == 'pass' or node.value == 'break' or node.value == 'continue' or node.value == 'yield' or node.value == 'raise':
    return NoOpCfgNode(node)
    # assert_unexpected_parso(False, node_info)

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
  def _create_cfg_node_for_import_name(self, node):
    # import_name: 'import' dotted_as_names
    # dotted_as_names: dotted_as_name (',' dotted_as_name)*
    # dotted_as_name: dotted_name ['as' NAME]
    # dotted_name: NAME ('.' NAME)*
    child = node.children[1]  # 0 is 'import'
    if child.type != 'dotted_as_names':
      path, as_name = path_and_name_from_import_child(child)
      return ImportCfgNode(
          path,
          as_name=as_name,
          parso_node=node,
          module_loader=self.module_loader)

    # Multiple imports.
    import_nodes = []
    out = GroupCfgNode(import_nodes, parso_node=node)
    dotted_as_names = child
    for child in dotted_as_names.children:
      if child.type == 'operator':
        assert_unexpected_parso(child.value == ',', node_info(child))
      else:
        path, as_name = path_and_name_from_import_child(child)
        import_nodes.append(
            ImportCfgNode(
                path,
                as_name=as_name,
                parso_node=node,
                module_loader=self.module_loader))
    return out

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
    # Example from . import y
    while path_node.type == 'operator' and (path_node.value == '.' or
                                            path_node.value == '...'):
      path += path_node.value
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
        except_nodes.append(
            ExceptCfgNode(AnonymousExpression(NONE_POBJECT), None, suite_node))
      else:
        assert keyword.type == 'except_clause'
        except_clause = keyword
        exceptions = expression_from_node(except_clause.children[1])
        if len(except_clause.children) == 4:
          exception_variable = VariableExpression(
              except_clause.children[-1].value)
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

    return TryCfgNode(
        try_suite,
        except_nodes,
        else_suite=else_suite,
        finally_suite=finally_suite)

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
    return KlassCfgNode(name, suite, module=self._module, parso_node=node)

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

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_star_expr(self, node):
    # StarredExpression itself can't be evaluated. This would actually be an illegal use that
    # shouldn't run, but we make do instead.
    return ExpressionCfgNode(expression_from_node(node.children[1]), node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_assert_stmt(self, node):
    # Note that we don't so much care about excuting this as extracting
    # used symbols from it.
    if len(node.children) == 2:
      return ExpressionCfgNode(
          expression_from_node(node.children[1]), node.children[1])
    assert len(node.children) == 4
    return GroupCfgNode([
        ExpressionCfgNode(
            expression_from_node(node.children[1]), node.children[1]),
        ExpressionCfgNode(
            expression_from_node(node.children[-1]), node.children[-1])
    ])

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_async_stmt(self, node):
    # TODO: https://docs.python.org/3/library/asyncio-task.html
    debug(f'Ignoring async in {node.type}')
    return self._create_cfg_node(node.children[1])

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_async_funcdef(self, node):
    # TODO: https://docs.python.org/3/library/asyncio-task.html
    # TODO: Generators.
    return self._create_cfg_node_for_funcdef(node.children[1])

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_decorated(self, node):
    # TODO: Handle first child decorator or decorators.
    assert_unexpected_parso(len(node.children) == 2, node_info(node))
    return self._create_cfg_node(node.children[1])

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_yield_expr(self, node):
    # TODO: Generators.
    return ReturnCfgNode(expression_from_node(node.children[1]), node)

  ##### Intentional NoOp nodes for our purposes. #####
  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_number(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_del_stmt(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_newline(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_endmarker(self, node):
    return NoOpCfgNode(node)

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_decorators(self, node):
    debug(f'Skipping {node.type}')

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_raise_stmt(self, node):
    debug(f'Skipping {node.type}')
    raise NotImplementedError(type(node))

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_global_stmt(self, node):
    raise NotImplementedError(type(node))

  @_assert_returns_type(CfgNode)
  def _create_cfg_node_for_nonlocal_stmt(self, node):
    raise NotImplementedError(type(node))

  ##### Functions that should never be called. #####

  # @_assert_returns_type(CfgNode)
  # def _create_cfg_node_for_flow_stmt(self, node):
  #   assert False  # treated as keyword
  #   # debug(f'Skipping {node.type}')
  #   # return NoOpCfgNode(node)

  # @_assert_returns_type(CfgNode)
  # def _create_cfg_node_for_break_stmt(self, node):
  #   debug(f'Skipping {node.type}')
  #   return NoOpCfgNode(node)

  # @_assert_returns_type(CfgNode)
  # def _create_cfg_node_for_continue_stmt(self, node):
  #   debug(f'Skipping {node.type}')
  #   return NoOpCfgNode(node)

  # @_assert_returns_type(CfgNode)
  # def _create_cfg_node_for_compound_stmt(self, node):
  #   assert False
  #   debug(f'Skipping {node.type}')
  #   return NoOpCfgNode(node)


def variables_from_node(node):
  if node.type == 'testlist_star_expr':
    return expression_from_testlist_comp(node)
  else:  # Illegal per the grammar, but this includes things like 'name'.
    variable = expression_from_node(node)
    if isinstance(variable,
                  (ItemListExpression, ListExpression, TupleExpression)):
      return variable
    assert isinstance(
        variable,
        (SubscriptExpression, AttributeExpression, VariableExpression))
    return ItemListExpression([variable])


@_assert_returns_type(CfgNode)
def statement_node_from_expr_stmt(node):
  # expr_stmt: testlist_star_expr (annassign | augassign (yield_expr|testlist) |
  #                   ('=' (yield_expr|testlist_star_expr))*)
  # annassign: ':' test ['=' test]
  # testlist_star_expr: (test|cf) (',' (test|star_expr))* [',']
  # augassign: ('+=' | '-=' | '*=' | '@=' | '/=' | '%=' | '&=' | '|=' | '^=' |
  #           '<<=' | '>>=' | '**=' | '//=')

  # Essentially, these are assignment expressions and can take a few forms:
  # a = b, a: List[type] = [...]
  # a,b = 1,2 or a,b = foo()
  # So, we need to handle essentially 1 or more things on the left and right
  # and possibly ignore a type hint in the assignment.
  child = node.children[0]

  variables = variables_from_node(child)
  if len(node.children) == 2:  # a += b - augmented assignment.
    annasign = node.children[1]
    assert_unexpected_parso(annasign.type == 'annassign', node_info(node))
    operator = annasign.children[-2]
    assert_unexpected_parso(operator.type == 'operator', node_info(node))
    value_node = annasign.children[-1]
    result_expression = expression_from_node(value_node)
    return AssignmentStmtCfgNode(
        variables,
        '=',
        result_expression,
        value_node=value_node,
        parso_node=node)
  else:
    value_node = node.children[-1]
    result_expression = expression_from_node(value_node)
    if len(node.children) == 3:  # a = b
      return AssignmentStmtCfgNode(
          variables,
          '=',
          result_expression,
          value_node=value_node,
          parso_node=node)

    # Example: a = b = ... = expr
    target_repeats = [variables]
    # Every other node is a variable - skip over '=' operators.
    for i in range(2, len(node.children) - 1, 2):
      child = node.children[i]
      if child.type == 'testlist_star_expr':
        target_repeats.append(expression_from_testlist_comp(child))
      else:  # Illegal per the grammar, but this includes things like 'name'.
        target_repeats.append(ItemListExpression([expression_from_node(child)]))
    assignments = []
    # Strictly speaking, this isn't perfectly accurate - i.e. each variable should be assigned
    # to the next variable - but I think it's fine to just skip them all to being assigned to the
    # final result?
    for target in target_repeats:
      assignments.append(
          AssignmentStmtCfgNode(
              target,
              '=',
              result_expression,
              value_node=value_node,
              parso_node=node))
    assert len(assignments) == len(node.children) // 2
    return GroupCfgNode(assignments, parso_node=node)


def _param_name_from_param_child(param_child):
  if param_child.type == 'name':
    return param_child.value
  assert_unexpected_parso(param_child.type == 'tfpdef')
  return param_child.children[0].value


@_assert_returns_type(List)
def parameters_from_parameters(node) -> List[Parameter]:
  assert_unexpected_parso(node.children[0].type == 'operator',
                          node_info(node))  # paran)
  out = []
  for param in node.children[1:-1]:  # Skip parens.
    if param.type == 'operator':
      # Either '*' or ',' - if *, is used, both will be given as children here.
      # All subsequent things are positional - don't care right now.
      continue

    assert_unexpected_parso(param.type == 'param', node_info(param))
    if len(param.children) == 1:  # name
      param_child = param.children[0]
      param_name = _param_name_from_param_child(param_child)
      out.append(Parameter(param_name, ParameterType.SINGLE))
    elif len(param.children) == 2:  # name, ',' OR *, args OR **, kwargs
      if param.children[1].type == 'operator' and param.children[1].value == ',':
        param_child = param.children[0]
        param_name = _param_name_from_param_child(param_child)
        out.append(Parameter(param_name, ParameterType.SINGLE))
      else:
        assert_unexpected_parso(param.children[0].type == 'operator',
                                node_info(param))
        if param.children[0].value == '*':
          out.append(
              Parameter(
                  _param_name_from_param_child(param.children[1]),
                  ParameterType.ARGS))
        else:  # **
          out.append(
              Parameter(
                  _param_name_from_param_child(param.children[1]),
                  ParameterType.KWARGS))
    elif len(param.children) == 3:  # len(3)
      if param.children[0].type == 'operator':
        if param.children[0].value == '*':
          out.append(
              Parameter(
                  _param_name_from_param_child(param.children[1]),
                  ParameterType.ARGS))
        else:  # **
          out.append(
              Parameter(
                  _param_name_from_param_child(param.children[1]),
                  ParameterType.KWARGS))
      elif param.children[0].type == 'name' or param.children[
          0].type == 'tfpdef':
        # TODO: typehint.
        out.append(
            Parameter(
                _param_name_from_param_child(param.children[0]),
                ParameterType.SINGLE,
                default_expression=expression_from_node(param.children[2])))
      else:
        assert_unexpected_parso(False)

    else:  # if len(param.children) == 4:  # name, =, expr, ','
      assert_unexpected_parso(len(param.children) == 4, node_info(param))
      out.append(
          Parameter(
              _param_name_from_param_child(param.children[0]),
              ParameterType.SINGLE,
              default_expression=expression_from_node(param.children[-2])))

  return out


@_assert_returns_type(Expression)
def expression_from_testlist_comp(node) -> Expression:
  # testlist_comp: (test|star_expr) ( comp_for | (',' (test|star_expr))* [','] )
  # expr(x) for x in b
  assert_unexpected_parso(
      len(node.children) != 2 or node.children[1].type == 'comp_for',
      ('Can\'t have comp_for references - only expressions.', node_info(node)))

  out = []
  for child in node.children:
    if child.type == 'operator':
      assert_unexpected_parso(child.value == ',')
      continue
    out.append(expression_from_node(child))
  return ItemListExpression(out)


def for_comprehension_from_comp_for(comp_for):
  target_variables = variables_from_node(comp_for.children[1])
  iterable_expression = expression_from_node(comp_for.children[3])

  assert len(comp_for.children) <= 5
  if len(comp_for.children) == 5:
    comp_iter = expression_from_node(comp_for.children[4])
  else:
    comp_iter = None
  return ForComprehension(target_variables, iterable_expression, comp_iter)


def expression_from_comp_for(generator_node,
                             comp_for) -> ForComprehensionExpression:
  # comp_iter: comp_for | comp_if
  # sync_comp_for: 'for' exprlist 'in' or_test [comp_iter]
  # comp_for: ['async'] sync_comp_for
  # comp_if: 'if' test_nocond [comp_iter]

  assert comp_for.type == 'comp_for'
  generator_expression = expression_from_node(generator_node)

  return ForComprehensionExpression(generator_expression,
                                    for_comprehension_from_comp_for(comp_for))


@_assert_returns_type(Expression)
def expression_from_testlist_comp(node) -> TupleExpression:
  # testlist_comp: (test|star_expr) ( comp_for | (',' (test|star_expr))* [','] )
  # expr(x) for x in b
  if len(node.children
        ) == 2 and node.children[1].type == 'comp_for':  # expr(x) for x in b
    return TupleExpression(expression_from_comp_for(*node.children))

    # return extract_references_from_comp_for(test, comp_for)
  else:  # expr(x), expr(b), ...,
    out = []
    for child in node.children:
      if child.type == 'operator' and child.value == ',':
        continue
      out.append(expression_from_node(child))
    return TupleExpression(ItemListExpression(out))


@_assert_returns_type(Expression)
def expression_from_testlist(node) -> ItemListExpression:
  out = []
  for child in node.children:
    if child.type == 'operator':
      assert_unexpected_parso(child.value == ',')
      continue
    out.append(expression_from_node(child))
  return ItemListExpression(out)


@_assert_returns_type(Expression)
def expression_from_atom_expr(node) -> Expression:
  # atom_expr: ['await'] atom trailer*
  # atom: ('(' [yield_expr|testlist_comp] ')' |j
  #       '[' [testlist_comp] ']' |
  #       '{' [dictorsetmaker] '}' |
  #       NAME | NUMBER | STRING+ | '...' | 'None' | 'True' | 'False')
  # trailer: '(' [arglist] ')' | '[' subscriptlist ']' | '.' NAME
  iterator = iter(node.children)
  reference_node = next(iterator)
  # Might be 'await' instead of an actual reference_node - fastforward if so.
  if reference_node.type == 'keyword' and reference_node.value == 'await':
    reference_node = next(iterator)

  # Should be an 'atom'.
  last_expression = expression_from_node(reference_node)
  # trailer: '(' [arglist] ')' | '[' subscriptlist ']' | '.' NAME
  for trailer in iterator:
    if trailer.children[0].value == '(':
      if len(trailer.children) == 2:  # Function call - ()
        last_expression = CallExpression(last_expression)
      else:

        args, kwargs = args_and_kwargs_from_arglist(trailer.children[1])
        last_expression = CallExpression(last_expression, args, kwargs)
    elif trailer.children[0].value == '[':
      subscript_expression = expressions_from_subscriptlist(trailer.children[1])
      last_expression = SubscriptExpression(last_expression,
                                            subscript_expression)
    else:
      assert_unexpected_parso(trailer.children[0].value == '.',
                              trailer.get_code())
      last_expression = AttributeExpression(last_expression,
                                            trailer.children[1].value)
  return last_expression


def _unimplmented_expression(func):

  @wraps(func)
  def wrapper(node):
    try:
      return func(node)
    except NotImplementedError:
      debug(f'Failing to handle node: {node_info(node)}')
      return UnknownExpression(node.get_code())

  return wrapper


@_unimplmented_expression
def expressions_from_subscriptlist(node) -> Expression:
  try:
    # subscriptlist: subscript (',' subscript)* [',']
    # subscript: test | [test] ':' [test] [sliceop]
    # sliceop: ':' [test]
    if node.type != 'subscriptlist' and node.type != 'subscript':
      expression = expression_from_node(node)
      assert isinstance(expression, Expression)
      return expression
    elif node.type == 'subscriptlist':
      values = ItemListExpression(
          list(
              itertools.chain(
                  expressions_from_subscriptlist(node) for node in
                  filter(lambda x: x.type != 'operator' or x.value != ',',
                         node.children))))
      assert all(isinstance(value, Expression) for value in values)
      return values
    else:  # subscript
      # num op num [sliceop]
      # info(f'Failing to handle node: {node_info(node)}')
      # return UnknownExpression(node.get_code())
      raise NotImplementedError()  # TODO
  except:
    return UnknownExpression(node.get_code())


# @_unimplmented_expression


def kwarg_from_argument(argument):
  # argument: ( test [comp_for] |
  #        test '=' test |
  #        '**' test |
  #        '*' test )
  # Note: We do an obnoxious amount of checking here to see if it's a kwarg because just checking
  # for 'name' first also matches for_comp - e.g. 'truth for truth in truths'. It's dumb.
  # first_child = node.children[0]
  first_child = argument.children[0]

  # Examples: *args or **kwargs
  if first_child.type == 'operator':
    assert first_child.value == '*' or first_child.value == '**'
    if len(argument.children) == 1:
      return None, '*'  # * - positional indicator.d
    return None, StarredExpression(first_child.value,
                                   expression_from_node(argument.children[1]))

  second_child = argument.children[1]
  if second_child.type == 'operator' and second_child.value == '=':
    # kwarg
    assert len(argument.children) == 3
    return first_child.value, expression_from_node(argument.children[2])

  first_expression = expression_from_node(first_child)
  assert second_child.type == 'comp_for'
  for_comprehension = for_comprehension_from_comp_for(second_child)
  return None, ForComprehensionExpression(first_expression, for_comprehension)

  # if argument.children[0].type == 'name':  # Possible kwarg
  #   if len(argument.children) == 3 and argument.children[1].type == 'operator' and argument.children.value == '=':
  #     return argument.children[0].value, expression_from_node(argument.children[2])
  #   assert False

  #   # elif argument.type == 'operator' and argument.value == '*':
  #   #   continue
  # else:  # arg
  #   assert_unexpected_parso(len(argument.children) == 2, node_info(argument))


@_assert_returns_type(Tuple)
def args_and_kwargs_from_arglist(node):
  try:
    if node.type != 'arglist' and node.type != 'argument':
      return [expression_from_node(node)], {}
    elif node.type == 'argument':
      name, arg = kwarg_from_argument(node)
      if name:
        return [], {name: arg}
      return [arg], {}
      # if first_child.type == 'name':
      #   second_child = node.children[1]
      #   if second_child.type == 'operator' and second_child.value == '=':  # kwarg
      #     return [], {first_child.value: expression_from_node(node.children[2])}
      #   else:  # comp_for
      #     assert_unexpected_parso(second_child.type == 'comp_for')
      #     raise NotImplementedError()

      # else:
      #   # Example: *args or **kwargs
      #   if first_child.type == 'operator':
      #     raise NotImplementedError()
      # assert_unexpected_parso(len(node.children) == 2, node_info(node))
      # raise NotImplementedError()

    else:  # arglist
      iterator = iter(node.children)
      args = []
      kwargs = {}
      for child in iterator:
        if child.type == 'argument':
          name, arg = kwarg_from_argument(child)
          if arg == '*':
            continue
          if name:
            kwargs[name] = arg
          else:
            args.append(arg)
        elif child.type != 'operator':  # not ','
          args.append(expression_from_node(child))
      return args, kwargs
  except NotImplementedError as e:
    debug(f'Failed to handle: {node_info(node)}')
    return [UnknownExpression(node.get_code())], {}


@_assert_returns_type(Expression)
def expression_from_node(node):
  if node.type == 'number':
    return LiteralExpression(num(node.value))
  if node.type == 'string':
    return LiteralExpression(node.value[1:-1])  # Strip surrounding quotes.
  if node.type == 'strings':
    return LiteralExpression(
        node.get_code().strip()
    )  #''.join(c.value[1:-1] for c in node.children))  # Strip surrounding quotes.
  if node.type == 'keyword':
    return LiteralExpression(keyword_eval(node.value))
  if node.type == 'operator' and node.value == '...':
    return LiteralExpression(keyword_eval(node.value))
  if node.type == 'name':
    return VariableExpression(node.value)
  if node.type == 'factor':
    return FactorExpression(node.children[0].value,
                            expression_from_node(node.children[1]), node)
  if node.type == 'arith_expr' or node.type == 'term':
    return expression_from_math_expr(node)
  if node.type == 'atom':
    return expression_from_atom(node)
  if node.type == 'atom_expr':
    return expression_from_atom_expr(node)
  if node.type == 'testlist_comp' or node.type == 'testlist_star_expr':
    return expression_from_testlist_comp(node)
  if node.type == 'testlist' or node.type == 'exprlist':
    return expression_from_testlist(node)
  if node.type == 'comparison':
    return expression_from_comparison(node)
  if node.type == 'test':
    return expression_from_test(node)
  if node.type == 'not_test':
    return NotExpression(expression_from_node(node.children[1]))
  if node.type == 'lambdef' or node.type == 'lambdef_nocond':
    debug(f'Failed to process lambdef - unknown.')
    return UnknownExpression(node.get_code())
  if node.type == 'fstring':
    debug(f'Failed to process fstring_expr - string.')
    return LiteralExpression(node.get_code())  # fstring_string type.
  if node.type == 'star_expr':
    return StarredExpression(node.children[0].value,
                             expression_from_node(node.children[-1]))
  if node.type == 'or_test' or node.type == 'and_test':
    return expression_from_and_test_or_test(node)

    # return UnknownExpression()
  debug(f'Unhanded type!!!!: {node_info(node)}')
  # return UnknownExpression(node.get_code())
  raise NotImplementedError(node_info(node))
  # assert_unexpected_parso(False, node_info(node))


def expression_from_and_test_or_test(node) -> Expression:
  assert len(node.children) >= 3
  right_expression = expression_from_node(node.children[-1])
  for i in range(1, len(node.children), 2)[::-1]:
    right_expression = AndOrExpression(
        expression_from_node(node.children[i - 1]), node.children[i].value,
        right_expression)
  return right_expression


def expression_from_dictorsetmaker(dictorsetmaker
                                  ) -> Union[SetExpression, DictExpression]:
  # dictorsetmaker:
  # dict case:
  #                 ((test ':' test | '**' expr)
  #                 (comp_for | (',' (test ':' test | '**' expr))* [',']))
  # set case:
  #                ((test | star_expr)
  #                 (comp_for | (',' (test | star_expr))* [',']))
  # Technically, shouldn't happen but does in cases like {1}.
  if not dictorsetmaker.type == 'dictorsetmaker':
    return SetExpression([expression_from_node(dictorsetmaker)])
  assignments = []
  iterator = iter(range(0, len(dictorsetmaker.children)))
  is_dict = is_set = False
  for i in iterator:
    child = dictorsetmaker.children[i]
    if child.type == 'operator':
      if child.value == '**' or child.value == '*':
        i = next(iterator)
        assignments.append(
            StarredExpression(child.value,
                              expression_from_node(dictorsetmaker.children[i])))
        if child.value == '**':
          is_dict = True
        else:
          is_set = True
      else:
        assert child.value == ','
      continue
    key = expression_from_node(child)

    if i + 1 == len(dictorsetmaker.children):
      assignments.append(key)
      break
    i = next(iterator)
    child = dictorsetmaker.children[i]
    if child.type == 'comp_for':
      is_set = True
      assignments.append(
          ForComprehensionExpression(key,
                                     for_comprehension_from_comp_for(child)))
      continue
    assert child.type == 'operator'
    if child.value == ',':
      is_set = True
      assignments.append(key)
      continue
    elif child.value == ':':
      is_dict = True
      i = next(iterator)
      value = expression_from_node(dictorsetmaker.children[i])
      if i + 1 == len(dictorsetmaker.children):
        assignments.append(KeyValueAssignment(key, value))
        break
      i = next(iterator)
      child = dictorsetmaker.children[i]
      if child.type == 'comp_for':
        assignments.append(
            KeyValueForComp(key, value, for_comprehension_from_comp_for(child)))
      else:
        assert child.type == 'operator' and child.value == ','
        assignments.append(KeyValueAssignment(key, value))
      continue
    assert False

  assert not (is_dict and is_set)
  if is_set:
    return SetExpression(assignments)

  return DictExpression(assignments)


@_assert_returns_type(Expression)
@_unimplmented_expression
def expression_from_atom(node):
  # atom: ('(' [yield_expr|testlist_comp] ')' |
  #       '[' [testlist_comp] ']' |
  #       NAME | NUMBER | STRING+ | '...' | 'None' | 'True' | 'False')

  if node.children[0].value == '(':
    # yield_expr|testlist_comp
    if node.children[1].type == 'keyword' and node.children[1].value == 'yield':
      raise NotImplementedError('Not yet handling yield_expr')
    elif len(node.children) == 2:
      return ItemListExpression([])
    else:
      assert_unexpected_parso(len(node.children) == 3, node_info(node))
      return expression_from_node(node.children[1])
  elif node.children[0].value == '[':
    if len(node.children) == 3:
      return expression_from_node(node.children[1])
      # if isinstance(inner_expr, ()):
      #   return inner_expr.expressions)
      # return ItemListExpression([inner_expr])
    assert len(node.children) == 2
    return ItemListExpression([])
  elif node.children[0].value == '{':
    # info(f'Doing dumb logic for dict.')
    # return LiteralExpression({})
    return expression_from_dictorsetmaker(node.children[1])
    # raise NotImplementedError('Not yet handling dictorsetmaker')
  else:
    raise ValueError(node_info(node))


@_assert_returns_type(Expression)
def expression_from_comparison(node):
  # comparison: expr (comp_op expr)*
  # <> isn't actually a valid comparison operator in Python. It's here for the
  # sake of a __future__ import described in PEP 401 (which really works :-)
  # comp_op: '<'|'>'|'=='|'>='|'<='|'<>'|'!='|'in'|'not' 'in'|'is'|'is' 'not'
  # TODO: Implement.
  # Handles operators & comp_op ('is' 'not')

  # Arbitrarily many: a < b < c < d <....
  assert len(node.children) % 2 == 1 and len(node.children) >= 3
  last_expression = None
  for i in range(0, len(node.children) - 2, 2):
    left_expression = expression_from_node(node.children[i])
    operator = node.children[i + 1].get_code().strip()
    right_expression = expression_from_node(node.children[i + 2])
    comparison = ComparisonExpression(
        left_expression=left_expression,
        operator=operator,
        right_expression=right_expression)
    if last_expression:
      last_expression = AndOrExpression(last_expression, 'and', comparison)
    else:
      last_expression = comparison
  return last_expression


@_assert_returns_type(Expression)
def expression_from_test(node):
  # a if b else c
  assert_unexpected_parso(len(node.children) == 5, node_info(node))
  true_expression = expression_from_node(node.children[0])
  conditional_expression = expression_from_node(node.children[2])
  false_expression = expression_from_node(node.children[-1])
  return IfElseExpression(true_expression, conditional_expression,
                          false_expression)


@_assert_returns_type(Expression)
@_unimplmented_expression
def expression_from_math_expr(node):
  # expr: xor_expr ('|' xor_expr)*
  # xor_expr: and_expr ('^' and_expr)*
  # and_expr: shift_expr ('&' shift_expr)*
  # shift_expr: arith_expr (('<<'|'>>') arith_expr)*
  # arith_expr: term (('+'|'-') term)*
  # term: factor (('*'|'@'|'/'|'%'|'//') factor)*
  # factor: ('+'|'-'|'~') factor | power
  # power: atom_expr ['**' factor]
  if len(node.children) != 3:
    # TODO: https://docs.python.org/3/reference/expressions.html#operator-precedence
    raise NotImplementedError()
  left_expression = expression_from_node(node.children[0])
  right_expression = expression_from_node(node.children[2])
  return MathExpression(
      left_expression,
      node.children[1].value,
      right_expression,
      parso_node=node)


def children_contains_operator(node, operator_str):
  for child in node.children:
    if child.type == 'operator' and child.value == operator_str:
      return True
  return False


def path_and_name_from_dotted_as_name(node):
  assert_unexpected_parso(node.type == 'dotted_as_name', node_info(node))
  if node.children[0].type == 'name':
    path = node.children[0].value
  else:
    dotted_name = node.children[0]
    assert_unexpected_parso(dotted_name.type == 'dotted_name',
                            node_info(dotted_name))
    path = path_from_dotted_name(dotted_name)
  if len(node.children) == 1:  # import x
    return path, None
  # import a as b
  assert_unexpected_parso(len(node.children) == 3, node_info(node))
  return path, node.children[-1].value


def path_from_dotted_name(dotted_name):
  return ''.join([child.value for child in dotted_name.children])


def path_and_name_from_import_child(child):
  if child.type == 'name':
    return child.value, None
  if child.type == 'dotted_as_name':
    return path_and_name_from_dotted_as_name(child)
  # Example: import a.b
  if child.type == 'dotted_name':
    return path_from_dotted_name(child), None


def path_to_name(node, name):
  if hasattr(node, 'value') and node.value == name:
    return (node,)
  if hasattr(node, 'children'):
    for child in node.children:
      x = path_to_name(child, name)
      if x is not None:
        return (node, *x)
  return None


def node_info(node):
  return (node.type, node.get_code())


def extract_nodes_of_type(node, type_, out=None):
  if out is None:
    out = []
  if node.type == type_:
    out.append(node)
  if hasattr(node, 'children'):
    for child in node.children:
      extract_nodes_of_type(child, type_, out)
  return out


def num(s):
  try:
    return int(s, 0)  # 0 allows hex to be read like 0xdeadbeef.
  except ValueError:
    try:
      return float(s)
    except ValueError:
      return complex(s)


def keyword_eval(keyword_str):
  if keyword_str == 'True':
    return True
  elif keyword_str == 'False':
    return False
  elif keyword_str == 'None':
    return None
  elif keyword_str == 'Ellipsis' or keyword_str == '...':
    return Ellipsis
  elif keyword_str == 'yield':
    return None
  assert_unexpected_parso(False, keyword_str)
