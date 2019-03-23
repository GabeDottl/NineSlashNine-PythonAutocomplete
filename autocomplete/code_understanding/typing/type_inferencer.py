'''The purpose of this module is to infer values and/or types of identifiers.

This is done through some static analysis, performing Good Enough Lazy Typing (TM).

Rather than trying to derive the exact value or type of a variable immediately,
instead, this creates Expressions which can be lazily evaluated to determine
the value of a reference - or more generally, what types it might be in the
current context.

In some cases, such as with parameters, we can't infer types directly. In these
cases, we may try to infer probable types based on the name of the variable
and the context.

For example, 'node' is used often in this file. This module knows nothing of
parso, so its not going to be able to infer that its type is always a parso
tree Node, but looking at the context in which node parameters are used
across this file, one can extrapolate that it will likely have members including
'children', 'type' and sometimes 'name' and 'value' - therefore, we can say
it's a DuckType with these possible members.
'''
import attr
from autocomplete.code_understanding.typing.utils import *

@attr.s
class Type:
  type_ = attr.ib()
  is_ambiguous = attr.ib(default=False)
  value = attr.ib(default=None)

@attr.s
class DuckType:
  members = attr.ib()

@attr.s
class TypeOf:
  expr = attr.ib()

@attr.s
class ComplexType:
  '''Class for types that are too complex to extrapolate.'''
  code = attr.ib()


class UnknownType:
  '''Types that are unknown.'''

@attr.s
class IndexOf:
  array = attr.ib()
  index = attr.ib()


class ResultOf:

  def __init__(self, call, *args, **kwargs):
    self.call = call
    self.args = args
    self.kwargs = kwargs

class Expression:
  def evaluate(self): # abstract
    raise NotImplementedError()


@attr.s
class LiteralExpression(Expression):
  literal = attr.ib()

  def evaluate(self):
    return self.literal

@attr.s
class CallExpression(Expression):
  function_reference = attr.ib()

  def evaluate(self):
    assert len(self.function_reference)
    function_assignment = self.function_reference.assignments[-1]
    assert isinstance(function_assignment.value, Function), function_assignment
    return function_assignment.value.returns

@attr.s
class ReferenceExpression(Expression):
  reference = attr.ib()
  def evaluate(self):
    if len(self.reference.assignments) == 0:
      raise ValueError()
    elif len(self.reference.assignments) == 1:
      return self.reference.assignments[0].value.evaluate()
    else:
      # TODO: Need to do more thorough evaluation of which assignment to use.
      raise NotImplementedError()

@attr.s
class IfExpression(Expression):
  positive_expression = attr.ib()
  conditional_expression = attr.ib()
  negative_expression = attr.ib()

  def evaluate(self):
    conditional = self.conditional_expression.evaluate()
    if not conditional:
      return self.negative_expression.evaluate()
    else:
      if conditional.is_ambiguous():
        return OneOf([self.positive_expression.evaluate(), self.negative_expression.evaluate()])
      else:
        return self.positive_expression.evaluate()

@attr.s
class ForExpression(Expression):
  generator_expression = attr.ib()
  conditional_expression = attr.ib()
  iterable_expression = attr.ib()

  def evaluate(self):
    return generator_expression.evaluate()

@attr.s
class OperatorExpression(Expression):
  left = attr.ib()
  operator = attr.ib()
  right = attr.ib()

  def evaluate(self):
    # expr: xor_expr ('|' xor_expr)*
    # xor_expr: and_expr ('^' and_expr)*
    # and_expr: shift_expr ('&' shift_expr)*
    # shift_expr: arith_expr (('<<'|'>>') arith_expr)*
    # arith_expr: term (('+'|'-') term)*
    # term: factor (('*'|'@'|'/'|'%'|'//') factor)*
    # factor: ('+'|'-'|'~') factor | power
    # power: atom_expr ['**' factor]
    # TODO: handle options...
    if self.operator == '+':
      return self.left.evaluate() + self.right.evaluate()
    return

@attr.s
class Function:
  returns = attr.ib()

class Klass:
  name = attr.ib()
  members = attr.ib()

class Instance:
  klass = attr.ib()

@attr.s
class ImportOf:
  path= attr.ib()

@attr.s
class ImportFrom:
  path= attr.ib(kw_only=True)
  name = attr.ib(kw_only=True)
  as_name = attr.ib(kw_only=True)

@attr.s
class Reference:
  name = attr.ib(kw_only=True)
  scope = attr.ib(kw_only=True)
  # unknown = attr.ib(False)
  temp = attr.ib(False, kw_only=True)

  def __attrs_post_init__(self):
    # Need this here lest all references share a single list
    self.assignments = []

  def get_complete_name(self):
    out = []
    scope = self.scope
    while scope:
      out.insert(0, scope.name)
      scope = scope.scope
    out.append(self.name)
    return ''.join(out)

@attr.s
class IndexReference:
  source_reference = attr.ib(kw_only=True)
  index = attr.ib(kw_only=True)
  assignments = []

@attr.s
class ReferenceAssignment:
  reference = attr.ib(kw_only=True)
  pos = attr.ib(kw_only=True)
  value = attr.ib(kw_only=True)


class TypeInferencer:
  references_dict = {}
  current_scope_path = [None]

  def reference_exists(self, name):
    return name in self.references_dict

  def find_reference(self, name):
    # TODO: Scoping!
    return self.references_dict[name]

  def add_reference(self, name, reference):
    # TODO: Scoping!
    self.references_dict[name] = reference

  def typify_tree(self, node):
    # Here, we essentially handle the higher-level nodes we might encounter
    # which are very generic.
    if node.type == 'newline' or node.type == 'endmarker' or node.type == 'keyword':
      return
    elif node.type == 'file_input' or node.type == 'suite':
      for child in node.children: self.typify_tree(child)
    elif node.type == 'import_name':
      self.handle_import_name(node)
    elif node.type == 'import_from':
      self.handle_import_from(node)
    elif node.type == 'classdef':
      self.handle_classdef(node)
    elif node.type == 'funcdef':
      self.handle_funcdef(node)
    elif node.type == 'decorated':
      # TODO: Handle decorators.
      self.typify_tree(node.children[1]) # node.children[0] is a decorator.
    elif node.type == 'async_stmt':
      self.typify_tree(node.children[1]) # node.children[0] is 'async'.
    elif node.type == 'if_stmt':
      self.handle_if_stmt(node)
    elif node.type == 'simple_stmt':
      self.handle_simple_stmt(node)
    elif node.type == 'expr_stmt':
      self.handle_expr_stmt(node)
    elif node.type == 'for_stmt':
      self.handle_for_stmt(node)
    elif node.type == 'while_stmt':
      self.handle_while_stmt(node)
    elif node.type == 'try_stmt':
      self.handle_try_stmt(node)
    elif node.type == 'with_stmt':
      self.handle_with_stmt(node)
    else:
      assert False, node_info(node)

  def handle_import_name(self, node):
    # import_name: 'import' dotted_as_names
    # dotted_as_names: dotted_as_name (',' dotted_as_name)*
    # dotted_as_name: dotted_name ['as' NAME]
    # dotted_name: NAME ('.' NAME)*
    child = node.children[1] # 0 is 'import'
    if child.type == 'dotted_as_name':
      self.import_dotted_as_name(child)
    else:
      assert child.type == 'dotted_as_names', node_info(child)
      # some combination of
      for child in dotted_as_names:
        if child.type == 'name':
          self.create_import_reference(child, child.value)
        elif child.type == 'operator':
          assert child.value == ',', node_info(child)
        else:
          assert child.type == 'dotted_as_name', node_info(child)
          self.import_dotted_as_name(child)


  def create_import_reference(self, node, path, from_import_name=None, as_name=None):
    # assert not (from_import_name and as_name), (from_import_name, as_name)
    if as_name is not None:
      name = as_name
    elif from_import_name is not None:
      name = from_import_name
    else:
      name = path

    reference = Reference(name=name, scope=self.current_scope_path[-1])
    if from_import_name and as_name:
      assignment = ReferenceAssignment(reference=reference, pos=node.start_pos, value=ImportFrom(path=path, name=from_import_name, as_name=as_name))
    elif from_import_name:
      assignment = ReferenceAssignment(reference=reference, pos=node.start_pos, value=ImportFrom(path=path, name=from_import_name, as_name=from_import_name))
    else:
      assignment = ReferenceAssignment(reference=reference, pos=node.start_pos, value=ImportOf(path))
    reference.assignments.append(assignment)
    self.add_reference(as_name, reference)


  def import_dotted_as_name(self, node):
    assert node.type == 'dotted_as_name', node_info(node)
    if node.children[0].type == 'name':
      path = node.children[0].value
    else:
      dotted_name = node.children[0]
      assert dotted_name.type == 'dotted_name', node_info(dotted_name)
      path = ''.join([child.value for child in dotted_name.children])
    if len(node.children) == 1: # import x
      self.create_import_reference(node, path)
    else:
      assert len(node.chilren) == 3, node_info(node) # import a as b
      self.create_import_reference(node, path, node.children[-1].value)

  def handle_import_from(self, node):
    # import_from: ('from' (('.' | '...')* dotted_name | ('.' | '...')+)
    #              'import' ('*' | '(' import_as_names ')' | import_as_names))
    # import_as_name: NAME ['as' NAME]
    # from is first child
    path_node_index = 1
    # First node after import might be '.' or '...' operators.
    path_node = node.children[path_node_index]
    path = ''
    if path_node.type == 'operator':
      path = path_node.value
      path_node_index +=1
      path_node = node.children[path_node_index]

    if path_node.type == 'name':
      path += path_node.value
    else:
      assert path_node.type == 'dotted_name', node_info(path_node)
      path += ''.join([child.value for child in path_node.children])
    # import is next node
    import_as_names = node.children[path_node_index + 2]
    if import_as_names.type == 'operator': # from x import (y)
      import_as_names = node.children[path_node_index + 3]
    if import_as_names.type == 'name':
      self.create_import_reference(node, path, from_import_name=import_as_names.value)
    else:
      assert import_as_names.type == 'import_as_names', node_info(import_as_names)
      for child in import_as_names.children:
        if child.type == 'name':
          self.create_import_reference(node, path, from_import_name=child.value)
        elif child.type == 'operator':
          assert child.value == ',', node_info(node)
        else:
          assert child.type == 'import_as_name', node_info(child)
          assert len(child.children) == 3, node_info(child)
          self.create_import_reference(node, path, from_import_name=child.children[0].value,  as_name=child.children[-1].value)


  def handle_classdef(self, node):
    reference = self._create_reference_and_assignment(node)
    self.current_scope_path.append(reference)
    # [keyword, name, operator] = class X: - skip these.
    for child in node.children[3:]:
      typify_tree(child)
    self.current_scope_path.pop()

  def handle_funcdef(self, node):
    reference = self._create_reference_and_assignment(node)
    self.current_scope_path.append(reference)
    # [keyword, name, parameters, operator, suite] = def foo(): suite
    assert len(node.children) == 5, node.get_code()
    self.handle_parameters(node.children[2])
    self.handle_suite(node.children[4])
    self.current_scope_path.pop()

  def handle_parameters(self, node):
    assert node.type == 'parameters', node_info(node)
    # First, positional or kwargs, then optionally *args, more kwargs, **kwargs
    # if len(node.children == 2):
    #   return # just ().

    # TODO: Handle self?
    # Don't really need to worry about things like *args, **kwargs, etc. here.
    for param_node in node.children[1:-1]: # skip operators on either end.
      assert param_node.type == 'param', (param_node.type, param_node.get_code())
      reference = Reference(name=param_node.name.value, scope=self.current_scope_path[-1])
      self.add_reference(param_node.name.value, reference)

  def handle_suite(self, node):
    assert node.type == 'suite', node_info(node)
    for child in node.children:
      self.typify_tree(node)

  def handle_simple_stmt(self, node):
    for child in node.children:
      self.typify_tree(child)

  def handle_expr_stmt(self, node):
    # Essentially, these are assignment expressions and can take a few forms:
    # a = b, a: List[type] = [...]
    # a,b = 1,2 or a,b = foo()
    # So, we need to handle essentially 1 or more things on the left and right
    # and possibly ignore a type hint in the assignment.
    testlist_star_expr = node.children[0]
    references = self.references_from_node(testlist_star_expr)
    if len(node.children) == 2: # a += b - augmented assignment.
      annasign = node.children[1]
      assert annasign.type == 'annassign', node_info(node)
      results = annasign.children[-1]
    else:
      assert len(node.children) == 3, node_info(node)
      results = node.children[-1]
    results = self.expression_from_node(results)
    self.create_assignments(references, results, node.start_pos)

  def create_assignments(self, references, results, pos):
    # TODO: ReferenceTuple?
    if not isinstance(references, (tuple, list)):
      assignment = ReferenceAssignment(reference=references, value=results, pos=pos)
      references.assignments.append(assignment)
    else:
      if isinstance(results, (tuple, list)) and len(references) == len(results):
        for reference, result in zip(references, results):
          self.create_assignments(reference, result)
      else:
        assert not isinstance(results, (tuple, list)), f'Incompatible shapes: {references}, {results}'
        for i, reference in enumerate(references):
          self.create_assignments(reference, IndexOf(results, i))

  def references_from_node(self, node):
    if node.type == 'name': # Simplest case - a=1
      if self.reference_exists(node.value):
        return self.find_reference(node.value)
      else:
        reference = Reference(name=node.value, scope=self.current_scope_path[-1])
        self.add_reference(node.value, reference)
        return reference
    elif node.type == 'testlist_star_expr':
      out = []
      for child in node.children:
        out.append(self.references_from_node(child))
      return out
    elif node.type == 'atom':
      child = node.children[0]
      if child.type == 'operator':
        assert len(node.children) == 3, node_info(node)
        if child.value == '(' or child.value == '[':
          return self.references_from_node(node.children[1])
        else:
          assert False, node_info(child)
      else:
        assert len(atom.children) == 1 and child.type == 'name', node_info(child)
        return self.references_from_node(child)
    elif node.type == 'atom_expr':
      return self.extract_reference_from_atom_expr(node)
    elif node.type == 'testlist_comp':
      return self.extract_references_from_testlist_comp(node)
    else:
      assert False, node_info(node)

  def extract_references_from_testlist_comp(self, node):
    # testlist_comp: (test|star_expr) ( comp_for | (',' (test|star_expr))* [','] )
    if len(node.children) == 2 and node.children[1].type == 'comp_for': # expr(x) for x in b
      assert False, ('Can\'t have comp_for references - only expressions.', node_info(node))
      # return self.extract_references_from_comp_for(test, comp_for)
    else: # expr(x), expr(b), ...,
      out = []
      for child in node.children:
        if child.type == 'operator':
          assert child.value == ','
          continue
        out.append(self.references_from_node(child))
      return out

  def extract_reference_from_atom_expr(self, node):
    # atom_expr: ['await'] atom trailer*
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
                value=ResultOf(self.find_reference(previous_name))))
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
                value=IndexOf(self.find_reference(previous_name), 0)))
        previous_name = None
      else:
        # TODO: handle previous node as reference
        assert trailer.children[0].value == '.', trailer.get_code()
        if previous_name:
          new_reference = Reference(name=previous_name, scope=last_reference)
        previous_name = trailer.children[1].value  # name
    if previous_name:
      new_reference = Reference(name=previous_name, scope=last_reference)




  def expression_from_node(self, node):
    if node.type == 'number':
      return LiteralExpression(num(node.value))
    elif node.type == 'string':
      return LiteralExpression(node.value[1:-1]) # Strip surrounding quotes.
    elif node.type == 'keyword':
      return LiteralExpression(keyword_eval(node.value))
    elif node.type == 'name':
      reference = self.find_reference(node.value)
      return ReferenceExpression(reference)
    elif node.type == 'arith_expr':
      return self.expression_from_arith_expr(node)
    else:
      assert False, node_info(node)

  def expression_from_arith_expr(self, node):
    assert len(node.children) == 3, node_info(node)
    left = self.expression_from_node(node.children[0])
    right = self.expression_from_node(node.children[2])
    return OperatorExpression(left=left, operator=node.children[1].value, right=right)



  def handle_for_stmt(self, node):
    for child in node.children:
      pass

  def handle_if_stmt(self, node):
    # # first child is 'if' keyword, next is conditional.
    # conditional = node.children[1]
    # # Next is ':', followed by some statement.
    # self.typify_tree(node.children[3])
    # if len(node.chilren) > 4:
    #   # elifs, else...
    iterator = iter(node.children)
    for child in iterator:
      try:
        if child.type == 'keyword':
          n = next(iterator) # Conditional expression or an operator.
          if n.type != 'operator': # if some conditional expression
            next(iterator) # Skip pass the operator
        else:
          self.typify_tree(child)
      except StopIteration:
        pass

  def handle_while_stmt(self, node):
    for child in node.children:
      pass

  def handle_try_stmt(self, node):
    for child in node.children:
      pass

  def handle_with_stmt(self, node):
    for child in node.children:
      pass

  # def expression_from_node_from_comp_for(self, expr, node):
  #   # sync_comp_for: 'for' exprlist 'in' or_test [comp_iter]
  #   # comp_for: ['async'] sync_comp_for
  #   # TODO: this.
  #   reference = Reference(name=expr.to_code(), scope=None)
  #   reference.assignments.append(ReferenceAssignment(reference=reference, value=node.to_code()))
  #   self.add_reference(reference)
  #   return reference

  def _create_reference_and_assignment(self, node):
    reference = Reference(name=node.name.value, scope=self.current_scope_path[-1])
    self.add_reference(node.name.value,  reference)
    reference_assignment = ReferenceAssignment(
        reference=reference, pos=node.start_pos, value=node.type)
    reference.assignments.append(reference_assignment)
    return reference

  def insert_name_types(self, node):
    if node.type == 'classdef' or node.type == 'funcdef':
      pass
    elif node.type == 'expr_stmt' and children_contains_operator(node, '='):
      left = node.children[0]
      right = node.children[2]
      results = eval_type(right)
      # TODO: Be more robust? E.g. a, (b,c).
      reference_assignments = get_reference_assignments(left)
      if len(reference_assignments) == 1:
        reference_assignments[0].type = results
      elif not isinstance(results, (tuple, list)):
        for i, reference_assignment in enumerate(reference_assignments):
          reference_assignment.type = IndexOf(results, i)
      else:
        for reference_assignment, result in zip(reference_assignments, results):
          reference_assignment.type = result

  def get_reference_assignments(self, node, first=True):
    reference = None
    if node.type == 'name':
      if self.reference_exists(node.value):
        reference = self.find_reference(node.value)
      else:
        reference = Reference(name=node.value, scope=scope)
        self.add_reference(node.value, reference)

    if node.type == 'atom_expr':
      reference = atom_expr_to_atom(node)

    if reference is not None:
      reference_assignment = ReferenceAssignment(
          reference=reference, pos=node.start_pos, value=None)
      reference.assignments.append(reference_assignment)
      return (reference_assignment,) if first else reference_assignment
    out = []
    try:
      for child in node.children:
        reference_assignments = get_reference_assignments(
            child, first=False)
        if reference_assignments:
          out.append(reference_assignments)
    except AttributeError:
      pass
    return out


  def node_to_reference_or_value(self, node):
    if hasattr(node, 'name'):
      return self.find_reference(node.name)
    else:
      reference = Reference(name='temp', scope=None, temp=True)
      ReferenceAssignment(
          reference=reference,
          pos=node.start_pos,
          value=eval_type(node))
      return
      # self.references_dict[temp_name(node)] = reference
    # return reference

  def eval_type(self, node):
    if node.type == 'name':
      return TypeOf(self.find_reference(node.value))
    if node.type == 'number' or node.type == 'str':
      return Type(node.type)
    return ComplexType(node.get_code())
