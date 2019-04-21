import itertools
from abc import ABC, abstractmethod
from builtins import NotImplementedError
from enum import Enum
from functools import partialmethod
from typing import List

import attr

from autocomplete.code_understanding.typing.errors import (
    LoadingModuleAttributeError, SourceAttributeError)
from autocomplete.nsn_logging import debug, info, warning

_OPERATORS = [
    '__add__', '__and__', '__ge__', '__gt__', '__le__', '__lt__', '__lshift__',
    '__mod__', '__mul__', '__ne__', '__or__', '__pow__', '__radd__', '__rand__',
    '__rdivmod__', '__rfloordiv__', '__rlshift__', '__rmod__', '__rmul__',
    '__sub__', '__truediv__', '__xor__'
]


class FuzzyBoolean(Enum):
  FALSE = 0
  MAYBE = 1
  TRUE = 2

  def invert(self):
    if self == FuzzyBoolean.FALSE:
      return FuzzyBoolean.TRUE
    if self == FuzzyBoolean.TRUE:
      return FuzzyBoolean.FALSE
    return FuzzyBoolean.MAYBE

  def __bool__(self):
    raise ValueError('FuzzyBoolean\s shouldn\'t be converted to regular bools')


class PObject(ABC):
  '''PObjects wrap or substitute actual objects and encapsulate unexpected or ambiguous behavior.

  For example, when a variable may have multiple types (FuzzyObject), is a totally unknown type
  and value (UnknownObject), or when an object is known but is used in seemingly illegal
  circumstances (AugmentedObject).

  In general, behavior is deferred to an 'actual' language object abstraction (Function, Klass,
  Instance, etc.) defined in the language_objects module.

  PObject stands for Python Object - because this is essentially the abstraction we use in lieu
  of the |object| type.
  '''

  @abstractmethod
  def has_attribute(self, name):
    ...

  @abstractmethod
  def get_attribute(self, name):
    ...

  @abstractmethod
  def set_attribute(self, name, value):
    ...

  @abstractmethod
  def apply_to_values(self, func):
    ...

  @abstractmethod
  def value_equals(self, other) -> FuzzyBoolean:
    ...

  @abstractmethod
  def value_is_a(self, type_) -> FuzzyBoolean:
    ...

  @abstractmethod
  def value(self) -> object:
    ...

  @abstractmethod
  def bool_value(self) -> FuzzyBoolean:
    ...

  @abstractmethod
  def call(self, args, kwargs, curr_frame):
    ...

  @abstractmethod
  def _get_item_processed(self, indicies):
    ...

  @abstractmethod
  def get_item(self, args):
    ...

  @abstractmethod
  def set_item(self, index, value):
    ...

  def __bool__(self):
    raise ValueError(
        'Dangerous use of PObject - just use is None or bool_value() to avoid ambiguity.'
    )


@attr.s(str=False, repr=False)
class DynamicContainer:
  attributes = attr.ib(factory=dict)

  def has_attribute(self, name):
    return name in self.attributes

  def get_attribute(self, name):
    try:
      return self.attributes[name]
    except KeyError:
      fv = UnknownObject(f'DV({name})')  # Hmm, DV? UV? Factory?
      self.attributes[name] = fv
      return fv

  def set_attribute(self, name, value):
    self.attributes[name] = value

  def __str__(self):
    return f'{list(self.attributes.keys())}'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
class UnknownObject(PObject):
  name = attr.ib()  # For recording source of value - e.g. functools.wraps.
  _dynamic_container = attr.ib(factory=DynamicContainer)

  def has_attribute(self, name):
    return self._dynamic_container.has_attribute(name)

  def get_attribute(self, name):
    return self._dynamic_container.get_attribute(name)

  def set_attribute(self, name, value):
    self._dynamic_container.set_attribute(name, value)

  def apply_to_values(self, func):
    func(self)

  def value_equals(self, other) -> FuzzyBoolean:
    return FuzzyBoolean.TRUE if self == other else FuzzyBoolean.MAYBE

  def value_is_a(self, type_) -> FuzzyBoolean:
    return FuzzyBoolean.MAYBE

  # TODO: Rename 'dereference'?
  def value(self) -> object:
    return None

  def bool_value(self) -> FuzzyBoolean:
    return FuzzyBoolean.MAYBE

  def call(self, args, kwargs, curr_frame):
    _process_args_kwargs(args, kwargs, curr_frame)
    return UnknownObject('Call?')

  def _get_item_processed(self, indicies):
    return UnknownObject('get_item?')

  def get_item(self, args):
    # TODO
    return UnknownObject('get_item?')

  def set_item(self, index, value):
    ...

  def __str__(self):
    return f'UO[{self._dynamic_container}]'

  def __repr__(self):
    return str(self)


def _process_args_kwargs(args, kwargs, curr_frame):
  '''Processes args & kwargs but does nothing with them.'''
  for arg in itertools.chain(args, kwargs.values()):
    arg.evaluate(curr_frame)


@attr.s(str=False, repr=False)
class AugmentedObject(PObject):  # TODO: CallableInterface
  _object = attr.ib()
  _dynamic_container = attr.ib(factory=DynamicContainer)

  def has_attribute(self, name):
    return self._object.has_attribute(
        name) or self._dynamic_container.has_attribute(name)

  def get_attribute(self, name):
    try:

      return self._object.get_attribute(name)
    except (SourceAttributeError, LoadingModuleAttributeError):
      # TODO: Log
      debug(f'Failed to access {name} from {self._object}')
      return self._dynamic_container.get_attribute(name)
    except AttributeError:  # E.g. <str>.get_attribute
      # TODO: Support for some native objects - str, int, list perhaps.
      debug(f'Failed to access {name} from {self._object}')
      return self._dynamic_container.get_attribute(name)

  def set_attribute(self, name, value):
    # Can this get messy at all?
    # if self._object.has_attribute(name):
    self._object.set_attribute(name, value)
    # else:
    #   self._dynamic_container.set_attribute(name, value)

  def apply_to_values(self, func):
    func(self._object)

  def value_equals(self, other) -> FuzzyBoolean:
    if isinstance(other, PObject):
      return other.value_equals(self._object)
    return FuzzyBoolean.TRUE if self._object == other else FuzzyBoolean.FALSE

  def value_is_a(self, type_) -> FuzzyBoolean:
    return FuzzyBoolean.TRUE if isinstance(self._object,
                                           type_) else FuzzyBoolean.FALSE

  def value(self) -> object:
    if isinstance(self._object, PObject):
      return self._object.value()
    return self._object

  def bool_value(self) -> FuzzyBoolean:
    value = self.value()
    if isinstance(value, FuzzyBoolean):
      return value
    return FuzzyBoolean.TRUE if value else FuzzyBoolean.FALSE

  def call(self, args, kwargs, curr_frame):
    if hasattr(self._object, 'call'):
      return self._object.call(args, kwargs, curr_frame)
    _process_args_kwargs(args, kwargs, curr_frame)
    return UnknownObject('Call?')

  def _get_item_processed(self, indicies):
    if hasattr(self._object, '_get_item_processed'):
      return self._object._get_item_processed(indicies)
    elif hasattr(self._object, '__getitem__'):
      try:
        # TODO: This is broken - Namespaces use the same thing for attributes and subscripts.
        return AugmentedObject(self._object.__getitem__(indicies))
      except (KeyError, IndexError, TypeError, SourceAttributeError,
              LoadingModuleAttributeError):
        pass
    return UnknownObject(f'{self._object}[{indicies}]')

  def get_item(self, args):
    if hasattr(self._object, 'get_item'):
      return self._object.get_item(args)
    return self._get_item_processed(_process_indicies(args))

  def set_item(self, index, value):
    warning(f'Skipping setting {self._object}[{index}] = {value}')

  def __str__(self):
    return f'AV({self._object}):[{self._dynamic_container}]'

  def __repr__(self):
    return str(self)


class EmptyFuzzyValueError(Exception):
  ...


@attr.s(str=False, repr=False)
class FuzzyObject(PObject):
  """A FuzzyObject is an abstraction over the result of executing an expression.

  A FuzzyObject may have multiple values representing the expression being
  executed from different paths with different results or perhaps having an
  inner experssion which has ambiguous results.

  The primary purpose of a FuzzyObject is to expose as much information about
  an expression's outcome as possible with minimal cost.

  In particular, we may know a function will return False or a np.ndarray. So
  we know one value it might have and type of other values it may have
  (np.ndarray).
  """

  _values: List = attr.ib()  # Tuple of possible values
  _source_node = attr.ib(None)  # type is CfgNode - circular dep breaks lint.

  @_values.validator
  def _values_valid(self, attribute, values):
    assert all(isinstance(value, PObject) for value in values)

  def __attrs_post_init(self):
    new_values = []
    for val in self._values:
      if isinstance(val, FuzzyObject):
        new_values += val._values
      elif not isinstance(val, PObject):
        new_values.append(AugmentedObject(val))
      else:
        new_values.append(val)
    self._values = new_values
    self.validate()

  def validate(self):
    assert all(isinstance(value, PObject) for value in self._values)

  def __str__(self):
    return f'FV({self._values}{self._source_node})'

  def __repr__(self):
    return str(self)

  def merge(self, other: 'FuzzyObject'):
    # dvs = list(filter(lambda x: x is not None, [self._dynamic_container, other._dynamic_container]))
    return FuzzyObject(self._values + other._values)

  def has_single_value(self):
    return len(self._values) == 1

  def value(self) -> object:
    if not self.has_single_value():
      raise ValueError(f'Does not have a single value: {self._values}')
    if isinstance(self._values[0], PObject):  # Follow the rabbit hole.
      return self._values[0].value()
    return self._values[0]

  # def could_be_true_or_false(self):
  #   # Ambiguous if there is a mix of False and True.
  #   return (any(self._values) and not all(self._values) and
  #           len(self._values) > 0)

  def has_attribute(self, name):
    return all([value.has_attribute(name) for value in self._values])

  # TODO Check _values

  def get_attribute(self, name) -> 'FuzzyObject':
    return FuzzyObject([value.get_attribute(name) for value in self._values])
    # results = []
    # for val in self._values:
    #     results.append(val.get_attribute(name))

    #   if hasattr(val, 'get_attribute') and val.has_attribute(name):
    #     results.append(val.get_attribute(name))

    # if matches:    #   if len(matches) > 1:
    #     return FuzzyObject(matches)
    #   return matches[0]

    # if self._
    # self._dynamic_container.get_attribute(name)
    # # if not self._dynamic_creation:
    # #   raise ValueError(f'No value with attribute for {name} on {self}')
    # info(
    #     f'Failed to find attribute {name}; creating an empty FuzzyObject for it.'
    # )
    # return FuzzyObject([], dynamic_creation=True)

  def set_attribute(self, name: str, value):
    if not isinstance(value, PObject):
      value = AugmentedObject(value)
    for val in self._values:
      val.set_attribute(name, value)

  def apply_to_values(self, func):
    for value in self._values:
      value.apply_to_values(func)

  def value_equals(self, other) -> FuzzyBoolean:
    truths = [value.value_equals(other) for value in self._values]
    if all(truth == FuzzyBoolean.TRUE for truth in truths):
      return FuzzyBoolean.TRUE
    elif any(truth == FuzzyBoolean.TRUE or truth == FuzzyBoolean.MAYBE
             for truth in truths):
      return FuzzyBoolean.MAYBE
    return FuzzyBoolean.FALSE

  def value_is_a(self, type_) -> FuzzyBoolean:
    truths = [value.value_is_a(type_) for value in self._values]
    if all(truth == FuzzyBoolean.TRUE for truth in truths):
      return FuzzyBoolean.TRUE
    elif any(truth == FuzzyBoolean.TRUE or truth == FuzzyBoolean.MAYBE
             for truth in truths):
      return FuzzyBoolean.MAYBE
    return FuzzyBoolean.FALSE

  def bool_value(self) -> FuzzyBoolean:
    truths = [value.bool_value() == FuzzyBoolean.TRUE for value in self._values]
    if all(truth for truth in truths):
      return FuzzyBoolean.TRUE
    elif any(truth for truth in truths):
      return FuzzyBoolean.MAYBE
    return FuzzyBoolean.FALSE

  def apply(self, func):
    for value in self._values:
      func(value)

  def call(self, args, kwargs, curr_frame):
    out = []
    for value in self._values:
      result = value.call(args, kwargs, curr_frame)
      assert isinstance(result, PObject)
      out.append(result)
    if len(out) > 1:
      return FuzzyObject(out)
    elif out:  # len(out) == 1
      return out[0]
    raise EmptyFuzzyValueError()
    # _process_args_kwargs(args, kwargs, curr_frame)  # No children means we
    # return UnknownObject(f'FV({args}, {kwargs})')

  def _get_item_processed(self, indicies):
    out = []
    for value in self._values:
      try:
        result = value._get_item_processed(indicies)
        assert isinstance(result, PObject)
        out.append(result)  # TODO: Add API get_item_processed_args
      except IndexError as e:
        warning(e)
        out.append(UnknownObject(f'{value}[{indicies}]'))
    if len(out) > 1:
      return FuzzyObject(out)
    elif out:  # len(out) == 1
      return out[0]
    return UnknownObject(f'FV[{indicies}]')

  def get_item(self, args):
    indicies = _process_indicies(args)
    return self._get_item_processed(indicies)

  def set_item(self, index, value):
    debug(f'Skipping setting {self._object}[{index}] = {value}')

  def _operator(self, other, operator):
    try:
      values = [getattr(self.value(), operator)(other.value())]
      assert all(isinstance(value, PObject) for value in values)
      return FuzzyObject(values)
    except ValueError:
      types = self._types.union(other._types)
      values = []
      for v1 in self._values:
        try:
          for v2 in other._values:
            result = getattr(v1, operator)(v2)
            assert isinstance(result, PObject)
            values.append(result)
        except TypeError:
          continue
      # for v in chain(self._values, other._values):
      #   types.append(fuzzy_types(v))
      return FuzzyObject(values, types)


# Add various operators too FuzzyObject class.
# for operator_str in _OPERATORS:
#   setattr(FuzzyObject, operator_str,
#           partialmethod(FuzzyObject._operator, operator=operator_str))


def _process_indicies(args):
  if not args:
    return tuple()
  return tuple(x.value() for x in args) if len(args) > 1 else args[0].value()


NONE_POBJECT = AugmentedObject(None)
# UNKNOWN_POBJECT = FuzzyObject()
