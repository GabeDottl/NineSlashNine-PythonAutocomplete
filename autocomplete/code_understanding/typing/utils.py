from typing import List, Tuple, Union

from autocomplete.code_understanding.typing.classes import (AssignmentExpressionStatement,
                                                            AttributeExpression,
                                                            CallExpression,
                                                            CFGNode,
                                                            Expression,
                                                            LiteralExpression,
                                                            OperatorExpression,
                                                            Reference,
                                                            ReferenceCall,
                                                            ReferenceExpression,
                                                            ReferenceName,
                                                            SubscriptExpression,
                                                            TupleExpression)


def statement_from_expr_stmt(node):
  # Essentially, these are assignment expressions and can take a few forms:
  # a = b, a: List[type] = [...]
  # a,b = 1,2 or a,b = foo()
  # So, we need to handle essentially 1 or more things on the left and right
  # and possibly ignore a type hint in the assignment.
  child = node.children[0]

  if child.type == 'testlist_star_expr':
    references = references_from_testlist_comp(node)
  else:
    references = [reference_from_node(child)]
  if len(node.children) == 2:  # a += b - augmented assignment.
    annasign = node.children[1]
    assert annasign.type == 'annassign', node_info(node)
    operator = annasign.children[-2]
    assert operator.type == 'operator', node_info(node)
    value_node = annasign.children[-1]
  else:
    assert len(node.children) == 3, node_info(node)
    operator = node.children[1]
    value_node = node.children[-1]
  result_expression = expression_from_node(value_node)
  return AssignmentExpressionStatement(references, operator.value,
                                       result_expression)


def create_expression_node_tuples_from_if_stmt(
    cfg_builder, node) -> List[Tuple[Expression, CFGNode]]:
  expression_node_tuples = []
  iterator = iter(node.children)
  for child in iterator:
    try:
      # Few cases:
      # 1) {if/elif} {conditional} : {suite}
      # 2) else : {suite}
      assert child.type == 'keyword', (node_info(node), node_info(child))
      conditional_or_op = next(
          iterator)  # Conditional expression or an operator.
      if conditional_or_op.type == 'operator':
        assert child.value == 'else' and conditional_or_op.value == ':', (
            conditional_or_op, child)
        expression = LiteralExpression(True)
      else:
        expression = expression_from_node(conditional_or_op)
        assert expression, node_info(child)
        n = next(iterator)  # Skip past the operator
        assert n.type == 'operator', node_info(n)
      content = next(iterator)
      cfg_node = cfg_builder.create_cfg_node(content)

      expression_node_tuples.append((expression, cfg_node))
    except StopIteration:
      pass
  return expression_node_tuples


def reference_from_node(node) -> Reference:
  if node.type == 'name':  # Simplest case - a=1
    return Reference([ReferenceName(node.value)])
  elif node.type == 'atom':
    # atom: ('(' [yield_expr|testlist_comp] ')' |
    #       '[' [testlist_comp] ']' |
    #       '{' [dictorsetmaker] '}' |
    #       NAME | NUMBER | STRING+ | '...' | 'None' | 'True' | 'False')
    child = node.children[0]
    if child.type == 'operator':
      assert len(node.children) == 3, node_info(node)
      if child.value == '(' or child.value == '[':
        return reference_from_node(node.children[1])
      else:
        assert False, node_info(child)
    else:
      assert len(node.children) == 1 and child.type == 'name', node_info(child)
      return reference_from_node(child)
  elif node.type == 'atom_expr':
    return reference_from_atom_expr(node)
  elif node.type == 'testlist_comp':
    return references_from_testlist_comp(node)
  else:
    assert False, node_info(node)


def references_from_testlist_comp(node) -> List[Reference]:
  # testlist_comp: (test|star_expr) ( comp_for | (',' (test|star_expr))* [','] )
  if len(node.children
        ) == 2 and node.children[1].type == 'comp_for':  # expr(x) for x in b
    assert False, ('Can\'t have comp_for references - only expressions.',
                   node_info(node))
    # return extract_references_from_comp_for(test, comp_for)
  else:  # expr(x), expr(b), ...,
    out = []
    for child in node.children:
      if child.type == 'operator':
        assert child.value == ','
        continue
      out.append(reference_from_node(child))
    return out


def expression_from_testlist_comp(node) -> TupleExpression:
  # testlist_comp: (test|star_expr) ( comp_for | (',' (test|star_expr))* [','] )
  if len(node.children
        ) == 2 and node.children[1].type == 'comp_for':  # expr(x) for x in b
    assert False, ('Don\'t support comp_for references - only expressions.',
                   node_info(node))
    # return extract_references_from_comp_for(test, comp_for)
  else:  # expr(x), expr(b), ...,
    out = []
    for child in node.children:
      if child.type == 'operator':
        assert child.value == ','
        continue
      out.append(expression_from_node(child))
    return TupleExpression(out)


def reference_from_atom_expr(node):
  expression = expression_from_atom_expr(node)
  assert False, node_info(node)


def expression_from_atom_expr(node) -> Expression:
  # atom_expr: ['await'] atom trailer*
  # atom: ('(' [yield_expr|testlist_comp] ')' |
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
    if trailer.children[0].value == '(':  # Function call
      if len(trailer.children) == 2:
        last_expression = CallExpression(last_expression)
      else:
        args, kwargs = args_and_kwargs_from_arglist(trailer.children[1])
        last_expression = CallExpression(last_expression, args, kwargs)
    elif trailer.children[0].value == '[':
      subscript_expressions = expressions_from_subscriptlist(
          trailer.children[1])
      last_expression = SubscriptExpression(last_expression,
                                            subscript_expressions)
    else:
      assert trailer.children[0].value == '.', trailer.get_code()
      last_expression = AttributeExpression(last_expression, trailer.children[1].value)
  return last_expression


def expressions_from_subscriptlist(
    node) -> Union[Expression, Tuple[Expression]]:
  # subscriptlist: subscript (',' subscript)* [',']
  # subscript: test | [test] ':' [test] [sliceop]
  # sliceop: ':' [test]
  if node.type != 'subscriptlist' and node.type != 'subscript':
    return expression_from_node(node)
  elif node.type == 'subscriptlist':
    return tuple(
        expressions_from_subscriptlist(node) for node in
        filter(lambda x: x.type != 'operator' or x.value != ',', node.children))
  else:  # subscript
    # num op num [sliceop]
    raise NotImplementedError()  # TODO


def args_and_kwargs_from_arglist(node):
  if node.type != 'arglist' and node.type != 'argument':
    return [expression_from_node(node)], {}
  elif node.type == 'argument':
    if node.children[0].type == 'name':  # kwarg
      return [], {
          node.children[0].value: expression_from_node(node.children[2])
      }
    else:
      assert len(node.children) == 2, node_info(node)
      raise NotImplementedError()  # *args or **kwargs

  else:  # arglist
    iterator = iter(node.children)
    args = []
    kwargs = {}
    for child in iterator:
      if child.type == 'argument':
        if child.children[0].type == 'name':  # kwarg
          kwargs[child.children[0].value] = expression_from_node(child.children[2])
        else:
          assert len(child.children) == 2, node_info(child)
          raise NotImplementedError()  # *args or **kwargs
      elif child.type != 'operator':  # not ','
        args.append(expression_from_node(child))
    return args, kwargs

def expression_from_node(node):
  if node.type == 'number':
    return LiteralExpression(num(node.value))
  elif node.type == 'string':
    return LiteralExpression(node.value[1:-1])  # Strip surrounding quotes.
  elif node.type == 'keyword':
    return LiteralExpression(keyword_eval(node.value))
  elif node.type == 'operator' and node.value == '...':
    return LiteralExpression(keyword_eval(node.value))
  elif node.type == 'name':
    reference = Reference([ReferenceName(node.value)])
    return ReferenceExpression(reference)
  elif node.type == 'arith_expr':
    return expression_from_arith_expr(node)
  elif node.type == 'atom':
    return expression_from_atom(node)
  elif node.type == 'atom_expr':
    return expression_from_atom_expr(node)
  elif node.type == 'testlist_comp':
    return expression_from_testlist_comp(node)
  else:
    assert False, node_info(node)


def expression_from_atom(node):
  # atom: ('(' [yield_expr|testlist_comp] ')' |
  #       '[' [testlist_comp] ']' |
  #       '{' [dictorsetmaker] '}' |
  #       NAME | NUMBER | STRING+ | '...' | 'None' | 'True' | 'False')
  if node.children[0].value == '(':
    # yield_expr|testlist_comp
    if node.children[1].type == 'keyword' and node.children[1].value == 'yield':
      raise NotImplementedError('Not yet handling yield_expr')
    else:
      assert len(node.children) == 3, node_info(node)
      return expression_from_node(node.children[1])
  elif node.children[0].value == '[':
    raise NotImplementedError('Not yet handling testlist_comp')
  elif node.children[0].value == '{':
    raise NotImplementedError('Not yet handling dictorsetmaker')
  else:
    raise ValueError(node_info(node))


def expression_from_arith_expr(node):
  assert len(node.children) == 3, node_info(node)
  left = expression_from_node(node.children[0])
  right = expression_from_node(node.children[2])
  return OperatorExpression(
      left=left, operator=node.children[1].value, right=right)


def children_contains_operator(node, operator_str):
  for child in node.children:
    if child.type == 'operator' and child.value == operator_str:
      return True
  return False


def path_to_name(node, name):
  try:
    if node.value == name:
      return (node,)
  except AttributeError:
    pass
  try:
    for child in node.children:
      x = path_to_name(child, name)
      if x is not None:
        return (node, *x)
  except AttributeError:
    pass
  return None


def node_info(node):
  return (node.type, node.get_code())


def extract_nodes_of_type(node, type_, out=None):
  if out is None:
    out = []
  if node.type == type_:
    out.append(node)
  try:
    for child in node.children:
      extract_nodes_of_type(child, type_, out)
  except AttributeError:
    pass
  return out


def num(s):
  try:
    return int(s)
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
  assert False, keyword_str
