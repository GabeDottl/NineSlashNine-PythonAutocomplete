from functools import partialmethod
from itertools import chain
from typing import Dict, List, Set

import attr

from autocomplete.nsn_logging import info

_OPERATORS = [
    # fv'__abs__',
    '__add__',
    '__and__',
    # '__bool__',
    # '__invert__',
    '__ge__',
    '__gt__',
    '__le__',
    '__lt__',
    '__lshift__',
    '__mod__',
    '__mul__',
    '__ne__',
    # '__neg__',
    # '__new__',
    '__or__',
    # '__pos__',
    '__pow__',
    '__radd__',
    '__rand__',
    '__rdivmod__',
    # '__reduce__',
    # '__reduce_ex__',
    # '__repr__',
    '__rfloordiv__',
    '__rlshift__',
    '__rmod__',
    '__rmul__',
    # '__ror__',
    # '__round__',
    # '__rpow__',
    # '__rrshift__',
    # '__rshift__',
    # '__rsub__',
    # '__rtruediv__',
    # '__rxor__',
    '__sub__',
    '__truediv__',
    # '__trunc__',
    '__xor__'
]
# # '__setattr__',
# '__sizeof__',
# '__str__',
# '__subclasshook__',


@attr.s(str=False, repr=False)
class DynamicValue:
  attributes = attr.ib(factory=dict)

  def has_attribute(self, name):
    return name in self.attributes

  def get_attribute(self, name):
    try:
      return self.attributes[name]
    except KeyError:
      fv = FuzzyValue()  # Hmm, DV? UV? Factory?
      self.attributes[name] = fv
      return fv

  def set_attribute(self, name, value):
    self.attributes[name] = value

  def __str__(self):
    return f'DV{list(self.attributes.keys())}'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
class UnknownValue:
  name = attr.ib()
  _dynamic_value = attr.ib(factory=DynamicValue)

  def has_attribute(self, name):
    return self._dynamic_value.has_attribute(name)

  def get_attribute(self, name):
    return self._dynamic_value.get_attribute(name)

  def set_attribute(self, name, value):
    self._dynamic_value.set_attribute(name, value)

@attr.s
class AugmentedValue:
  value = attr.ib()
  _dynamic_value = attr.ib(factory=DynamicValue)

  def has_attribute(self, name):
    return self.value.has_attribute(name) or self._dynamic_value.has_attribute(name)

  def get_attribute(self, name):
    try:
      return self.value.get_attribute(name)
    except ValueError:
      # TODO: Log
      return self._dynamic_value.get_attribute(name)
    # return self._dynamic_value.get_attribute(name)

  def set_attribute(self, name, value):
    # Can this get messy at all?
    if self.value.has_attribute(name):
      self.value.set_attribute(name)
    else:
      self._dynamic_value.set_attribute(name)


@attr.s(str=False, repr=False)
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
  _source_node: 'CfgNode' = attr.ib(None)

  def __attrs_post_init(self):
    new_values = []
    for val in self._values:
      if not isinstance(val, AugmentedValue):
        new_values.append(AugmentedValue(val))
      else:
        new_values.append(val)
    self._values = new_values

  # TODO: unexecuted_expressions?

  def __str__(self):
    return f'FV({self._values}{self._source_node})'

  def __repr__(self):
    return str(self)

  def merge(self, other: 'FuzzyValue'):
    # dvs = list(filter(lambda x: x is not None, [self._dynamic_value, other._dynamic_value]))
    return FuzzyValue(
        self._values + other._values)

  # def is_ambiguous_type(self):
  #   return (len(self._values) + len(self._types)) != 1

  # def get_possible_types(self):
  #   return self._types + tuple(type(x) for x in self._values)

  def has_single_value(self):
    return len(self._values) == 1

  def is_completely_ambiguous(self):
    return len(self._values) == 0 and len(self._types) == 0

  def value(self):
    if not self.has_single_value():
      raise ValueError(f'Does not have a single value: {self._values}')
    if isinstance(self._values[0], FuzzyValue):  # Follow the rabbit hole.
      return self._values[0].value()
    return self._values[0]

  def could_be_true_or_false(self):
    # Ambiguous if there is a mix of False and True.
    return (any(self._values) and not all(self._values) and
            len(self._values) > 0)

  # def has_attribute(self, name):
    # TODO Check _values
    

  def get_attribute(self, name) -> 'FuzzyValue':
    return FuzzyValue([value.get_attribute(name) for value in self._values])
    # results = []
    # for val in self._values:
    #     results.append(val.get_attribute(name))
        
    #   if hasattr(val, 'get_attribute') and val.has_attribute(name):
    #     results.append(val.get_attribute(name))

    # if matches:
    #   if len(matches) > 1:
    #     return FuzzyValue(matches)
    #   return matches[0]

    # if self._
    # self._dynamic_value.get_attribute(name)
    # # if not self._dynamic_creation:
    # #   raise ValueError(f'No value with attribute for {name} on {self}')
    # info(
    #     f'Failed to find attribute {name}; creating an empty FuzzyValue for it.'
    # )
    # return FuzzyValue([], dynamic_creation=True)

  def set_attribute(self, name: str, value):
    if not isinstance(value, (FuzzyValue, AugmentedValue, UnknownValue)):
      value = AugmentedValue(value)
    for value in self._values:
      value.set_attribute(name, value)

  def apply(self, func):
    for value in self._values:
      func(value)

  def _operator(self, other, operator):
    try:
      return FuzzyValue([getattr(self.value(), operator)(other.value())])
    except ValueError:
      types = self._types.union(other._types)
      values = []
      for v1 in self._values:
        try:
          for v2 in other._values:
            values.append(getattr(v1, operator)(v2))
        except TypeError:
          continue
      # for v in chain(self._values, other._values):
      #   types.append(fuzzy_types(v))
      return FuzzyValue(values, types)

  def __getitem__(self, index):
    if self.has_single_value():
      if hasattr(self.value(), '__getitem__'):
        return FuzzyValue((self.value()[index],))
      return self
    raise NotImplementedError()


# Add various operators too FuzzyValue class.
for operator_str in _OPERATORS:
  setattr(FuzzyValue, operator_str,
          partialmethod(FuzzyValue._operator, operator=operator_str))

def literal_to_fuzzy(value):
  return FuzzyValue([value])

NONE_FUZZY_VALUE = literal_to_fuzzy(None)
# UNKNOWN_FUZZY_VALUE = FuzzyValue()