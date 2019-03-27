from typing import List

from autocomplete.code_understanding.typing.classes import (AssignmentExpressionStatement,
                                                            CallExpression,
                                                            Expression,
                                                            LiteralExpression,
                                                            OperatorExpression,
                                                            Reference,
                                                            ReferenceCall,
                                                            ReferenceExpression,
                                                            ReferenceName)


def statement_from_expr_stmt(node):
  # Essentially, these are assignment expressions and can take a few forms:
  # a = b, a: List[type] = [...]
  # a,b = 1,2 or a,b = foo()
  # So, we need to handle essentially 1 or more things on the left and right
  # and possibly ignore a type hint in the assignment.
  child = node.children[0]

  if child.type == 'testlist_star_expr':
    references = extract_references_from_testlist_comp(node)
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
        return references_from_node(node.children[1])
      else:
        assert False, node_info(child)
    else:
      assert len(node.children) == 1 and child.type == 'name', node_info(child)
      return references_from_node(child)
  elif node.type == 'atom_expr':
    return extract_reference_from_atom_expr(node)
  elif node.type == 'testlist_comp':
    return extract_references_from_testlist_comp(node)
  else:
    assert False, node_info(node)


def extract_references_from_testlist_comp(node) -> List[Reference]:
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


def extract_reference_from_atom_expr(node):
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

  last_reference = node_to_reference_or_value(reference_node)
  previous_name = None
  # trailer: '(' [arglist] ')' | '[' subscriptlist ']' | '.' NAME
  for trailer in iterator:
    if trailer.children[0].value == '(':
      # TODO: func call
      last_reference = Reference(name='temp', scope=last_reference, temp=True)
      # TODO: Handle function args.
      last_reference.assignments.append(
          ReferenceAssignment(
              reference=last_reference,
              pos=trailer.start_pos,
              value=ResultOf(find_reference(previous_name))))
      previous_name = None
    elif trailer.children[0].value == '[':
      # TODO: array access
      # TODO: func call
      last_reference = Reference(name='temp', scope=last_reference, temp=True)
      # TODO: Handle index params.
      last_reference.assignments.append(
          ReferenceAssignment(
              reference=last_reference,
              pos=trailer.start_pos,
              value=IndexOf(find_reference(previous_name), 0)))
      previous_name = None
    else:
      # TODO: handle previous node as reference
      assert trailer.children[0].value == '.', trailer.get_code()
      if previous_name:
        new_reference = Reference(name=previous_name, scope=last_reference)
      previous_name = trailer.children[1].value  # name
  if previous_name:
    new_reference = Reference(name=previous_name, scope=last_reference)


def expression_from_node(node):
  if node.type == 'number':
    return LiteralExpression(num(node.value))
  elif node.type == 'string':
    return LiteralExpression(node.value[1:-1])  # Strip surrounding quotes.
  elif node.type == 'keyword':
    return LiteralExpression(keyword_eval(node.value))
  elif node.type == 'name':
    reference = Reference([ReferenceName(node.value)])
    return ReferenceExpression(reference)
  elif node.type == 'arith_expr':
    return expression_from_arith_expr(node)
  else:
    assert False, node_info(node)


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
  assert False, keyword_str
