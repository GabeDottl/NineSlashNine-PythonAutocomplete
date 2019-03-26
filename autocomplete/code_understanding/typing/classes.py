import attr
from typing import List
from enum import Enum
# @attr.s
# class Type:
#   type_ = attr.ib()
#   is_ambiguous = attr.ib(default=False)
#   value = attr.ib(default=None)
#
# @attr.s
# class TypeOf:
#   expr = attr.ib()

# class ResultOf:
#
#   def __init__(self, call, *args, **kwargs):
#     self.call = call
#     self.args = args
#     self.kwargs = kwargs
# class UnknownType:
#   '''Types that are unknown.'''

# @attr.s
# class ComplexType:
#   '''Class for types that are too complex to extrapolate.'''
#   code = attr.ib()

# @attr.s
# class IndexOf:
#   array = attr.ib()
#   index = attr.ib()

@attr.s
class DuckType:
  members = attr.ib()
  common_aliases = attr.ib(factory=list) # e.g. 'node', 'child'


@attr.s
class FuzzyValue:
  '''A FuzzyValue is an abstraction over the result of executing an expression.

  A FuzzyValue may have multiple values representing the expression being
  executed from different paths with different results or perhaps having an
  inner experssion which has ambiguous results.

  The primary purpose of a FuzzyValue is to expose as much information about
  an expression's outcome as possible with minimal cost.

  In particular, we may know a function will return False or a np.ndarray. So
  we know one value it might have and type of other values it may have
  (np.ndarray).
  '''

  _values = attr.ib() # Tuple of possible values
  # is_ambiguous = attr.ib()
  _types = attr.ib(factory=list) # Tuple of possible types
  # TODO: unexecuted_expressions?

  def merge(self, other):
    return Result(self._values + other._values, self._types + other._types)

  def is_ambiguous_type(self):
    return (len(self._values) + len(self._types)) != 1

  def get_possible_types(self):
    return self._types + tuple(type(x) for x in self._values)

  def has_single_value(self):
    return len(self._values) == 1

  def is_completely_ambiguous(self):
    return len(self._values) == 0 and len(self._types) == 0

  def value(self):
    if not self.has_single_value():
      raise ValueError(f'Does not have a single value: {self.values}')
    return self._values[0]

  def could_be_true_or_false(self):
    # Ambiguous if there is a mix of False and True.
    return (any(self._values) and not all(self._values) and len(self._values) > 0)

  def __getitem__(self, index):
    if self.has_single_value() and hasattr(self.value(), '__getitem__'):
      return FuzzyValue((self.value()[index],))
    else:
      raise NotImplementedError()

none_fuzzy_value = FuzzyValue((None,))
unknown_fuzzy_value = FuzzyValue(tuple())

def literal_to_fuzzy(value):
  return FuzzyValue((value,))

class FunctionDef:
  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    # Create new frame
    # Process subgraph
    pass

class Expression:
  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    raise NotImplementedError() # abstract

@attr.s
class LiteralExpression(Expression):
  literal = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    return literal_to_fuzzy(self.literal)

@attr.s
class CallExpression(Expression):
  function_reference = attr.ib()
  args = attr.ib(factory=list)
  kwargs = attr.ib(factory=dict)

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    function_assignment = curr_frame.get_assignment(self.function_reference)
    return function_assignment.evaluate(curr_frame, prev_frame)
    # function_assignment = self.function_name.assignments[-1]
    # assert isinstance(function_assignment.value, Function), function_assignment
    # return function_assignment.value.returns

@attr.s
class ReferenceExpression(Expression):
  name = attr.ib()
  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    return curr_frame.get_assignment(name)

@attr.s
class IfExpression(Expression):
  positive_expression = attr.ib()
  conditional_expression = attr.ib()
  negative_expression = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    conditional = self.conditional_expression.evaluate(curr_frame, prev_frame)
    if not conditional:
      return self.negative_expression.evaluate(curr_frame, prev_frame)
    else:
      if conditional.is_ambiguous():
        return OneOf([self.positive_expression.evaluate(curr_frame, prev_frame), self.negative_expression.evaluate(curr_frame, prev_frame)])
      else:
        return self.positive_expression.evaluate(curr_frame, prev_frame)

@attr.s
class ForExpression(Expression):
  generator_expression = attr.ib()
  conditional_expression = attr.ib()
  iterable_expression = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    return generator_expression.evaluate(curr_frame, prev_frame)

@attr.s
class OperatorExpression(Expression):
  left = attr.ib()
  operator = attr.ib()
  right = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
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
      return self.left.evaluate(curr_frame, prev_frame) + self.right.evaluate(curr_frame, prev_frame)
    return

@attr.s
class AssignmentExpressionStatement: # Looks like an Expression, but not technically one.
  left_identifiers = attr.ib()
  operator = attr.ib() # Generally equals, but possibly +=, etc.
  right_expression = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    # TODO: Handle operator.
    result = right_expression.evaluate(curr_frame, prev_frame)
    if len(self.left_identifiers) == 1:
      curr_frame[self.left_identifiers[0]] = result
    for i, identifier in enumerate(self.left_identifiers):
      curr_frame[self.left_identifiers[0]] = result[i]

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
  # List of some combination of Names (str), CallExpression, and ArrayAccessExpression.
  # For example, a.b().c[0].d would roughly translate to:
  # Reference(ArrayAccessExpression(Reference(CallExpression(Reference(a.b), c), 0), d)
  # The magic for evaluating this is in the Frame class.
  sequence: List = attr.ib()



# @attr.s
# class Reference:
#   name = attr.ib(kw_only=True)
#   scope = attr.ib(kw_only=True)
#   # unknown = attr.ib(False)
#   temp = attr.ib(False, kw_only=True)
#
#   def __attrs_post_init__(self):
#     # Need this here lest all references share a single list
#     self.assignments = []
#
#   def get_complete_name(self):
#     out = []
#     scope = self.scope
#     while scope:
#       out.insert(0, scope.name)
#       scope = scope.scope
#     out.append(self.name)
#     return ''.join(out)

# @attr.s
# class IndexReference:
#   source_reference = attr.ib(kw_only=True)
#   index = attr.ib(kw_only=True)
#   assignments = []


#
# @attr.s
# class ReferenceAssignment:
#   reference = attr.ib(kw_only=True)
#   pos = attr.ib(kw_only=True)
#   value = attr.ib(kw_only=True)
#

class Frame:
  __slots__ = 'globals', 'locals', 'builtins'
  def __init__(self, globals, locals):
    self.globals = globals
    self.locals = locals
    self.builtins = [] # TODO


  def make_child(self) -> 'Frame':
    return Frame(self.globals + self.locals, [])

  def __getitem__(self, reference):
    return self.get_assignment(reference)

  def get_assignment(self, reference):
    first_identifier = reference.get_first_identifier()
    for group in (self.locals, self.globals, self.builtins):
      # Given a.b.c, Python will take the most-local definition of a and
      # search from there.
      if first_identifier in group:
        return group[reference]

    # TODO: lineno, frame contents.
    raise ValueError(f'{reference} doesn\'t exist in current context!')

class MemberDict:

  def __init__(self, name):
    self.name = name
    self._values = {}

  def __getitem__(self, reference):
    first_identifier = reference.get_first_identifier()
    if first_identifier not in self._values:
      return False
    reference = self._values[first_identifier]
    if first_identifier.is_name
    if len()

  def __setitem__(self, reference):
    first_identifier = reference.get_first_identifier()
    if first_identifier not in self._values:
      return False
    reference = self._values[first_identifier]

  def __contains__(self, reference):
    try:
      self[reference]
      return True
    except KeyError:
      return False

class KlassMemberDict(MemberDict):
  pass



# Node creation:
class CFGNode:
  def process(self, curr_frame, prev_frame):
    raise NotImplementedError() # abstract

# class Statement:
#   def evaluate(self, curr_frame, prev_frame):



class StmtCFGNode(CFGNode):
  __slots__ = 'statement', 'next_node'

  def __init__(self, statement):
    self.statement = statement
    self.next_node = None

  def process(self, curr_frame, prev_frame):
    self.statement.evaluate(curr_frame, prev_frame)
    if self.next_node:
      self.next_node.process(curr_frame, prev_frame)

class IfCFGNode(CFGNode):
  __slots__ = 'expression_node_tuples'

  def __init__(self, expression_node_tuples):
    '''For 'else', (True, node)'''
    self.expression_node_tuples = expression_node_tuples


  def process(self, curr_frame, prev_frame):
    for expression, node in self.expression_node_tuples:
      result = expression.run(curr_frame, prev_frame)
      if result.has_single_value() and result.value():
        # Expression is definitely true - evaluate and stop here.
        node.process(curr_frame, prev_frame)
        break
      elif result.has_single_value() and not result.value():
        # Expression is definitely false - skip.
        continue
      else: # Completely ambiguous.
        node.process(curr_frame, prev_frame)

class ClassCFGNode(CFGNode):
  def __init__(self, name, children):
    # TODO: Add to reference dict?
    self.name = name
    self.children = children

  def process(self, curr_frame, prev_frame):
    curr_frame.locals[self.name] = Klass

class GroupCFGNode(CFGNode):
  def __init__(self, children):
    self.children = children

  def process(self, curr_frame, prev_frame):
    for child in self.children: child.process(curr_frame, prev_frame)


class FuncCFGNode(CFGNode):
  def __init__(self, children):
    self.children = children

  def process(self, curr_frame, prev_frame):
    new_frame = curr_frame.make_child()
    for child in self.children: child.process(new_frame, curr_frame)
    # TODO: new_frame.finish?


@attr.s
class IfCFGNode(CFGNode):

  def __attrs_post_init__(self):
    self.children = []

  def id(self):
    return self.__hash__()

def is_linear_collection(type_str):
  return type_str == 'file_input' or type_str == 'suite' or type_str == 'classdef' or type_str == 'with_stmt'
