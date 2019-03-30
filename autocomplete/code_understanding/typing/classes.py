from enum import Enum
from itertools import chain
from typing import Dict, List, Set

import attr

from autocomplete.nsn_logging import info

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
#   """Types that are unknown."""

# @attr.s
# class ComplexType:
#   """Class for types that are too complex to extrapolate."""
#   code = attr.ib()

# @attr.s
# class IndexOf:
#   array = attr.ib()
#   index = attr.ib()


@attr.s
class DuckType:
  members = attr.ib()
  common_aliases = attr.ib(factory=list)  # e.g. 'node', 'child'


@attr.s
class FuzzyValue:
  """A FuzzyValue is an abstraction over the result of executing an expression.

  A FuzzyValue may have multiple values representing the expression being
  executed from different paths with different results or perhaps having an
  inner experssion which has ambiguous results.

  The primary purpose of a FuzzyValue is to expose as much information about
  an expression's outcome as possible with minimal cost.

  In particular, we may know a function will return False or a np.ndarray. So
  we know one value it might have and type of other values it may have
  (np.ndarray).
  """

  _values: List = attr.ib()  # Tuple of possible values
  # is_ambiguous = attr.ib()
  _types: Set = attr.ib(factory=set)  # Tuple of possible types
  _attributes: Dict = attr.ib(factory=dict)

  # TODO: unexecuted_expressions?

  def merge(self, other: 'FuzzyValue'):
    return FuzzyValue(self._values + other._values, self._types + other._types)

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
    return (any(self._values) and not all(self._values) and
            len(self._values) > 0)

  # def assign(self, fv: FuzzyValue):
  #   self._values = fv._values
  #   self._types = fv._types
  #   self._attributes = fv._attributes

  def getattribute(self, name):
    # TODO Check _values
    if name in self._attributes:
      return self._attributes[name]
    for val in self._values:
      if hasattr(val, name):
        return val.__getattribute__(name)
    info(f'Failed to find attribute {name}')
    return FuzzyValue([])

  def setattribute(self, name, value):
    self._attributes[name] = value

  def __add__(self, other):
    try:
      return FuzzyValue([self.value() + other.value()])
    except ValueError:
      types = self._types.union(other._types)
      values = []
      for v1 in self._values:
        try:
          for v2 in other._values:
            values.append(v1 + v2)
        except TypeError:
          continue
      for v in chain(self._values, other._values):
        types.append(fuzzy_types(v))
      return FuzzyValue(values, types)

  def __getitem__(self, index):
    if self.has_single_value():
      if hasattr(self.value(), '__getitem__'):
        return FuzzyValue((self.value()[index],))
      return self
    raise NotImplementedError()


def literal_to_fuzzy(value):
  return FuzzyValue([value])


def fuzzy_types(val):
  if not isinstance(val, FuzzyValue):
    return (type(val),)
  return val.get_possible_types()


none_fuzzy_value = literal_to_fuzzy(None)
unknown_fuzzy_value = FuzzyValue(tuple())


class FunctionDef:

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    # Create new frame
    # Process subgraph
    pass


class Expression:

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    raise NotImplementedError()  # abstract


@attr.s
class LiteralExpression(Expression):
  literal = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    return literal_to_fuzzy(self.literal)


@attr.s
class TupleExpression(Expression):
  expressions = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    return FuzzyValue(
        [tuple(e.evaluate(curr_frame, prev_frame) for e in self.expressions)])


@attr.s
class CallExpression(Expression):
  function_variable = attr.ib()
  args = attr.ib(factory=list)
  kwargs = attr.ib(factory=dict)

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    function_assignment = curr_frame.get_assignment(self.function_variable)
    return function_assignment.evaluate(curr_frame, prev_frame)
    # function_assignment = self.function_name.assignments[-1]
    # assert isinstance(function_assignment.value, Function), function_assignment
    # return function_assignment.value.returns


@attr.s
class AttributeExpression(Expression):
  base_expression = attr.ib()
  attribute = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    value = self.base_expression.evaluate(curr_frame, prev_frame)
    return value.__getattribute__(self.attribute)


@attr.s
class SubscriptExpression(Expression):
  base_expression = attr.ib()
  subscript_list = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    value = self.base_expression.evaluate(curr_frame, prev_frame)
    return value[tuple(e.evaluate() for e in self.subscript_list)]


@attr.s
class VariableExpression(Expression):
  name = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    return curr_frame.get_assignment(self)


@attr.s
class IfExpression(Expression):
  positive_expression = attr.ib()
  conditional_expression = attr.ib()
  negative_expression = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    conditional = self.conditional_expression.evaluate(curr_frame, prev_frame)
    if not conditional:
      return self.negative_expression.evaluate(curr_frame, prev_frame)
    if conditional.is_ambiguous():
      out = FuzzyValue()
      out._values = [
          self.positive_expression.evaluate(curr_frame, prev_frame),
          self.negative_expression.evaluate(curr_frame, prev_frame)
      ]
      return out
    return self.positive_expression.evaluate(curr_frame, prev_frame)


@attr.s
class ForExpression(Expression):
  generator_expression = attr.ib()
  conditional_expression = attr.ib()
  iterable_expression = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    return self.generator_expression.evaluate(curr_frame, prev_frame)


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
      return self.left.evaluate(curr_frame, prev_frame) + self.right.evaluate(
          curr_frame, prev_frame)
    assert False, f'Cannot handle {self.operator} yet.'


@attr.s
class AssignmentExpressionStatement:  # Looks like an Expression, but not technically one.
  left_variables = attr.ib()
  operator = attr.ib()  # Generally equals, but possibly +=, etc.
  right_expression = attr.ib()

  def evaluate(self, curr_frame, prev_frame) -> FuzzyValue:
    # TODO: Handle operator.
    result = self.right_expression.evaluate(curr_frame, prev_frame)
    info(f'result: {result}')
    info(f'self.right_expression: {self.right_expression}')
    if len(self.left_variables) == 1:
      curr_frame[self.left_variables[0]] = result
      info(f'result: {result}')
      info(
          f'curr_frame[self.left_variables[0]]: {curr_frame[self.left_variables[0]]}'
      )
    else:
      for i, variable in enumerate(self.left_variables):
        # TODO: Handle this properly...
        curr_frame[variable] = result[i]


@attr.s
class Function:
  params = attr.ib()
  returns = attr.ib()


@attr.s
class Klass:
  module = attr.ib()
  name = attr.ib()
  members = attr.ib()


@attr.s
class Instance:
  klass = attr.ib()

  # def __attrs_post_init__(self):
  #   self.members = copy(self.klass.members)


@attr.s
class ImportOf:
  path = attr.ib()


@attr.s
class ImportFrom:
  path = attr.ib(kw_only=True)
  name = attr.ib(kw_only=True)
  as_name = attr.ib(kw_only=True)


# @attr.s  #(frozen=True) # hashable
# class Variable:
#   # List of some combination of Names (str), CallExpression, and ArrayAccessExpression.
#   # For example, a.b().c[0].d would roughly translate to:
#   # Variable(ArrayAccessExpression(Variable(CallExpression(Variable(a.b), c), 0), d)
#   # Variable([Name(a), Name(b), Call(c, *args), Index(d, *args)])
#   # The magic for evaluating this is in the Frame class.
#   sequence: List = attr.ib()
#   # def __hash__(self):
#   #   return tuple(self.sequence).__hash__()
#
#
# @attr.s  #(frozen=True) # hashable
# class VariableName:
#   name = attr.ib()
#   # def __hash__(self): return hash(tuple(self.name))
#   # def __eq__(self, other): return self.name == other.name
#
#
# @attr.s  # #(frozen=True) # hashable
# class VariableCall:
#   name = attr.ib()
#   args = attr.ib(factory=tuple)
#   kwargs = attr.ib(factory=dict)
#   # def __hash__(self):
#   #   return hash(self.name) + hash(tuple())
#
#
# @attr.s  #(frozen=True) # hashable
# class VariableArrayAccess:
#   name = attr.ib()
#   args = attr.ib(factory=tuple)

# @attr.s
# class Variable:
#   name = attr.ib(kw_only=True)
#   scope = attr.ib(kw_only=True)
#   # unknown = attr.ib(False)
#   temp = attr.ib(False, kw_only=True)
#
#   def __attrs_post_init__(self):
#     # Need this here lest all variables share a single list
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
# class IndexVariable:
#   source_variable = attr.ib(kw_only=True)
#   index = attr.ib(kw_only=True)
#   assignments = []

#
# @attr.s
# class VariableAssignment:
#   variable = attr.ib(kw_only=True)
#   pos = attr.ib(kw_only=True)
#   value = attr.ib(kw_only=True)
#


@attr.s
class Parameter:
  name = attr.ib()
  type = attr.ib()
  default = attr.ib(None)


class ParameterType(Enum):
  SINGLE = 0
  ARGS = 1
  KWARGS = 2


Variable = Expression


class Frame:
  # __slots__ = 'globals', 'locals', 'builtins'
  def __init__(self, globals_, locals_):
    self.globals: Dict = globals_
    self.locals: Dict = locals_
    self.builtins: Dict = {}  # TODO
    self.returns: List[FuzzyValue] = []

  def make_child(self) -> 'Frame':
    return Frame({**self.globals, **self.locals}, {})

  def __getitem__(self, variable: Variable):
    return self.get_assignment(variable)

  def __setitem__(self, variable: Variable, value: FuzzyValue):
    # assert isinstance(variable, Variable), variable
    if isinstance(variable, VariableExpression):
      self.locals[variable.name] = value
    else:
      assert isinstance(variable, AttributeExpression), variable
      fuzzy_value = variable.base_expression.evaluate(self, None)
      fuzzy_value.setattribute(variable.attribute, value)
      # if len(variable.sequence) == 2:
      #   base = self.locals[variable.sequence[0].name]
      # else:
      #   base = self.get_assignment(Variable(variable.sequence[:-1]))

      # setattr(base, variable.sequence[1], value)
    # TODO: Handle nonlocal & global keyword states.

  def get_assignment(self, variable: Variable) -> FuzzyValue:
    if isinstance(variable, AttributeExpression):
      fuzzy_value = variable.base_expression.evaluate(self, None)
      return fuzzy_value.getattribute(variable.attribute)
    assert isinstance(variable, VariableExpression), variable

    name = variable.name
    for group in (self.locals, self.globals, self.builtins):
      # Given a.b.c, Python will take the most-local definition of a and
      # search from there.
      if name in group:
        return group[name]
        # # Variable([Name(a), Name(b), Call(c, *args), Index(d, *args)])
        # for identifier in variable_iter:
        #   fuzzy_value = getattr(fuzzy_value, identifier.name)
        #   if isinstance(identifier, VariableName):
        #     continue
        #   elif isinstance(identifier, VariableCall):
        #     fuzzy_value = self._invoke_call(fuzzy_value, identifier)
        #   elif isinstance(identifier, VariableArrayAccess):
        #     fuzzy_value = self._invoke_array_access(fuzzy_value, identifier)
        #   else:
        #     assert False, identifier
        # return fuzzy_value
    # TODO: lineno, frame contents.
    raise ValueError(f'{variable} doesn\'t exist in current context!')

  #
  # def _invoke_call(self, call_variable, identifier):
  #   devariabled_args = [self.get_assignment(arg) for arg in identifier.args]
  #   devariabled_kwargs = {
  #       k: self.get_assignment(v) for k, v in identifier.kwargs.items()
  #   }
  #   return call_variable(*devariabled_args, **devariabled_kwargs)
  #
  # def _invoke_array_access(self, call_variable, identifier):
  #   devariabled_args = [self.get_assignment(arg) for arg in identifier.args]
  #   raise NotImplementedError()
  #   return call_variable  #[*devariabled_args]

  def add_return(self, value):
    self.returns.append(value)

  def get_returns(self):
    return self.returns

  def __str__(self):
    return f'{[self.locals, self.globals, self.builtins]}\n'


# class MemberDict:
#
#   def __init__(self, name):
#     self.name = name
#     self._values = {}
#
#   def __getitem__(self, variable):
#     first_identifier = variable.get_first_identifier()
#     if first_identifier not in self._values:
#       return False
#     variable = self._values[first_identifier]
#     raise NotImplementedError() # TODO: FINISH!
#     # if first_identifier.is_name
#     # if len()
#
#   def __setitem__(self, variable):
#     first_identifier = variable.get_first_identifier()
#     if first_identifier not in self._values:
#       return False
#     variable = self._values[first_identifier]
#
#   def __contains__(self, variable):
#     try:
#       self[variable]
#       return True
#     except KeyError:
#       return False
#
# class KlassMemberDict(MemberDict):
#   pass


# Node creation:
class CfgNode:

  def process(self, curr_frame, prev_frame):
    raise NotImplementedError()  # abstract

@attr.s
class ExpressionCfgNode:
  expression = attr.ib()
  def process(self, curr_frame, prev_frame):
    self.expression.evaluate(curr_frame, prev_frame)


class NoOpCfgNode(CfgNode):

  def process(self, curr_frame, prev_frame):
    pass


class StmtCfgNode(CfgNode):
  # TypeError: descriptor 'statement' for 'StmtCfgNode' objects doesn't apply to 'StmtCfgNode' object
  # __slots__ = 'statement', 'next_node' # TODO Figure out why this is broken.

  def __init__(self, statement, code=''):
    self.statement = statement
    self.next_node = None
    self.code = code

  def process(self, curr_frame, prev_frame):
    self.statement.evaluate(curr_frame, prev_frame)
    if self.next_node:
      self.next_node.process(curr_frame, prev_frame)

  def __str__(self):
    return self._to_str()

  def _to_str(self):
    out = []
    if self.code:
      out.append(f'{self.__class__.__name__}: {self.code}')
    if self.next_node:
      out.append(str(self.next_node))
    return '\n'.join(out)


class IfCfgNode(CfgNode):
  # __slots__ = 'expression_node_tuples'

  def __init__(self, expression_node_tuples):
    """For 'else', (True, node)"""
    self.expression_node_tuples = expression_node_tuples

  def process(self, curr_frame, prev_frame):
    for expression, node in self.expression_node_tuples:
      result = expression.evaluate(curr_frame, prev_frame)
      if result.has_single_value() and result.value():
        # Expression is definitely true - evaluate and stop here.
        node.process(curr_frame, prev_frame)
        break
      elif result.has_single_value() and not result.value():
        # Expression is definitely false - skip.
        continue
      else:  # Completely ambiguous.
        node.process(curr_frame, prev_frame)


class ClassCfgNode(CfgNode):

  def __init__(self, name, children):
    # TODO: Add to variable dict?
    self.name = name
    self.children = children

  def process(self, curr_frame, prev_frame):
    curr_frame.locals[self.name] = Klass


class GroupCfgNode(CfgNode):

  def __init__(self, children):
    self.children = children

  def process(self, curr_frame, prev_frame):
    for child in self.children:
      child.process(curr_frame, prev_frame)

  def __str__(self):
    return '\n'.join([str(child) for child in self.children])


@attr.s
class FuncExpression(Expression):
  parameters = attr.ib()
  graph = attr.ib()

  def evaluate(self, curr_frame, prev_frame):
    new_frame = curr_frame.make_child()
    self.graph.process(new_frame, curr_frame)

    returns = new_frame.get_returns()
    if not returns:
      return none_fuzzy_value
    out = returns[0]
    for ret in returns[1:]:
      out = out.merge(ret)
    return out


@attr.s
class StubFuncExpression(Expression):
  parameters = attr.ib()
  returns = attr.ib()

  def evaluate(self, curr_frame, prev_frame):
    # TODO: Handle parameters.
    return self.returns


@attr.s
class FuncCfgNode(CfgNode):
  name = attr.ib()
  parameters = attr.ib()
  suite = attr.ib()

  def process(self, curr_frame, prev_frame):
    processed_params = []
    for param in self.parameters:
      if param.default is None:
        processed_params.append(param)
      else:  # Process parameter defaults at the time of definition.
        default = param.default.evaluate(curr_frame, prev_frame)
        processed_params.append(Parameter(param.name, param.type, default))
    curr_frame[VariableExpression(self.name)] = FuncExpression(
        processed_params, self.suite)

  def __str__(self):
    return f'def {self.name}({self.parameters}):\n  {self.suite}\n'


@attr.s
class ReturnCfgNode(CfgNode):
  expression = attr.ib()

  def process(self, curr_frame, prev_frame):
    curr_frame.add_return(self.expression.evaluate(curr_frame, prev_frame))


def is_linear_collection(type_str):
  return type_str == 'file_input' or type_str == 'suite' or type_str == 'classdef' or type_str == 'with_stmt'
