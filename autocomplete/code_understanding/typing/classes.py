from itertools import chain
from typing import Dict, List, Set

import attr

from autocomplete.nsn_logging import info

#
# @attr.s
# class Function:
#   params = attr.ib()
#   returns = attr.ib()
#   type = attr.ib(FunctionType.FREE)

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
#
# @attr.s
# class DuckType:
#   members = attr.ib()
#   common_aliases = attr.ib(factory=list)  # e.g. 'node', 'child'
#


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
    if isinstance(self._values[0], FuzzyValue):  # Follow the rabbit hole.
      return self._values[0].value()
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


NONE_FUZZY_VALUE = literal_to_fuzzy(None)
UNKNOWN_FUZZY_VALUE = FuzzyValue(tuple())


@attr.s
class ImportOf:
  path = attr.ib()


@attr.s
class ImportFrom:
  path = attr.ib(kw_only=True)
  name = attr.ib(kw_only=True)
  as_name = attr.ib(kw_only=True)


def is_linear_collection(type_str):
  return type_str == 'file_input' or type_str == 'suite' or type_str == 'classdef' or type_str == 'with_stmt'
