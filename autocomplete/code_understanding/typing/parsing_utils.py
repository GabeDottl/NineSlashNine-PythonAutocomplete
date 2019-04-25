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
    AttributeExpression, CallExpression, ComparisonExpression, DictExpression,
    Expression, FactorExpression, ForComprehension, ForComprehensionExpression,
    IfElseExpression, ItemListExpression, KeyValueAssignment, KeyValueForComp,
    ListExpression, LiteralExpression, MathExpression, NotExpression,
    SetExpression, StarredExpression, SubscriptExpression, TupleExpression,
    UnknownExpression, Variable, VariableExpression)
from autocomplete.code_understanding.typing.language_objects import (
    Parameter, ParameterType)
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


def variables_from_node(node):
  if node.type == 'testlist_star_expr':
    return ItemListExpression(expressions_from_testlist_comp(node))
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
        target_repeats.append(expressions_from_testlist_comp(child))
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
                default=expression_from_node(param.children[2])))
      else:
        assert_unexpected_parso(False)

    else:  # if len(param.children) == 4:  # name, =, expr, ','
      assert_unexpected_parso(len(param.children) == 4, node_info(param))
      out.append(
          Parameter(
              _param_name_from_param_child(param.children[0]),
              ParameterType.SINGLE, expression_from_node(param.children[-2])))

  return out


@_assert_returns_type(List)
def expressions_from_testlist_comp(node) -> List[Variable]:
  # testlist_comp: (test|star_expr) ( comp_for | (',' (test|star_expr))* [','] )
  if len(node.children
        ) == 2 and node.children[1].type == 'comp_for':  # expr(x) for x in b
    assert_unexpected_parso(
        False, ('Can\'t have comp_for references - only expressions.',
                node_info(node)))
    # return extract_references_from_comp_for(test, comp_for)
  else:  # expr(x), expr(b), ...,
    out = []
    for child in node.children:
      if child.type == 'operator':
        assert_unexpected_parso(child.value == ',')
        continue
      out.append(expression_from_node(child))
    return out


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
  if len(node.children
        ) == 2 and node.children[1].type == 'comp_for':  # expr(x) for x in b
    return TupleExpression(expression_from_comp_for(*node.children))

  # expr(x) for x in b
  if len(node.children) == 2 and node.children[1].type == 'comp_for':
    assert_unexpected_parso(
        False, ('Don\'t support comp_for references - only expressions.',
                node_info(node)))

    # return extract_references_from_comp_for(test, comp_for)
  else:  # expr(x), expr(b), ...,
    out = []
    for child in node.children:
      if child.type == 'operator':
        assert_unexpected_parso(child.value == ',')
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
  if node.type == 'testlist_comp':
    return expression_from_testlist_comp(node)
  if node.type == 'testlist' or node.type == 'exprlist':
    return expression_from_testlist(node)
  if node.type == 'comparison':
    return expression_from_comparison(node)
  if node.type == 'test':
    return NotExpression(expression_from_test(node))
  if node.type == 'not_test':
    return NotExpression(expression_from_node(node.children[1]))
  if node.type == 'lambdef':
    debug(f'Failed to process lambdef - unknown.')
    return UnknownExpression(node.get_code())
  if node.type == 'fstring':
    debug(f'Failed to process fstring_expr - string.')
    return LiteralExpression(node.get_code())  # fstring_string type.
  if node.type == 'star_expr':
    return StarredExpression(node.children[0].value,
                             expression_from_node(node.children[-1]))
    # return UnknownExpression()
  debug(f'Unhanded type!!!!: {node_info(node)}')
  return UnknownExpression(node.get_code())
  # raise NotImplementedError(node_info(node))
  # assert_unexpected_parso(False, node_info(node))


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
  operator = node.children[1].get_code().strip(
  )  # Handles operators & comp_op ('is' 'not')
  assert_unexpected_parso(len(node.children) == 3, node_info(node))
  left_expression = expression_from_node(node.children[0])
  right_expression = expression_from_node(node.children[2])
  return ComparisonExpression(
      left_expression=left_expression,
      operator=operator,
      right_expression=right_expression)


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
    return float(s)


def keyword_eval(keyword_str):
  if keyword_str == 'True':
    return True
  elif keyword_str == 'False':
    return False
  elif keyword_str == 'None':
    return None
  elif keyword_str == 'Ellipsis' or keyword_str == '...':
    return Ellipsis
  assert_unexpected_parso(False, keyword_str)


def print_tree(node, indent='', file=sys.stdout):
  print(f'{indent}{node.type}', file=file)
  if hasattr(node, 'children'):
    for c in node.children:
      print_tree(c, indent + '  ', file=file)
