import itertools
import types
import typing
from abc import ABC, abstractmethod
from builtins import NotImplementedError
from enum import Enum
from functools import partialmethod, wraps
from typing import Dict, List

import attr

from autocomplete.code_understanding.typing.errors import (
    AmbiguousFuzzyValueDoesntHaveSingleValueError, LoadingModuleAttributeError,
    NoDictImplementationError, SourceAttributeError)
from autocomplete.nsn_logging import debug, error, info, warning

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
    raise ValueError('FuzzyBoolean\'s shouldn\'t be converted to regular bools')

  def and_expr(self, other):
    assert isinstance(other, FuzzyBoolean)
    # if hasattr(other, bool_value):
    if self == FuzzyBoolean.FALSE or other == FuzzyBoolean.FALSE:
      return FuzzyBoolean.FALSE
    elif self == FuzzyBoolean.TRUE and other == FuzzyBoolean.TRUE:
      return FuzzyBoolean.TRUE
    return FuzzyBoolean.MAYBE if self.maybe_true() and other.maybe_true(
    ) else FuzzyBoolean.FALSE

  def or_expr(self, other):
    assert isinstance(other, FuzzyBoolean)
    # if hasattr(other, bool_value):
    if self == FuzzyBoolean.FALSE and other == FuzzyBoolean.FALSE:
      return FuzzyBoolean.FALSE
    elif self == FuzzyBoolean.TRUE or other == FuzzyBoolean.TRUE:
      return FuzzyBoolean.TRUE
    return FuzzyBoolean.MAYBE if self.maybe_true() or other.maybe_true(
    ) else FuzzyBoolean.FALSE

  def maybe_true(self):
    return self == FuzzyBoolean.MAYBE or self == FuzzyBoolean.TRUE


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
  def call(self, curr_frame, args, kwargs):
    ...

  @abstractmethod
  def get_item_pobject_index(self, indicies):
    ...

  @abstractmethod
  def get_item(self, curr_frame, index_expression):
    ...

  @abstractmethod
  def set_item(self, curr_frame, index_expression, value_expression):
    ...

  # def set_item_native_index(self, native_indicies, value):
  #   pass

  def iterator(self):
    return iter([])

  def hash_value(self):
    return hash(self.value())

  def to_dict(self):
    '''Stand-in for __dict__.'''
    raise NoDictImplementationError()
    # assert False, 'Not Implemented.'  # Don't want to be caught by normal NotImplementedError logic..

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

  def call(self, curr_frame, args, kwargs):
    # TODO: For some reason, this causes infinite recursion. Figure out why and uncomment.
    # _process_args_kwargs(curr_frame, args, kwargs)
    return UnknownObject('Call?')

  def get_item_pobject_index(self, native_indicies):
    return UnknownObject('get_item?')

  def get_item(self, curr_frame, index_expression):
    # TODO
    # index_expression.evaluate()
    return UnknownObject('get_item?')

  def set_item(self, curr_frame, index_expression, value_expression):
    # index_expression.evaluate()
    # value_expression.evaluate()
    ...

  def __str__(self):
    return f'UO[{self._dynamic_container}]'

  def __repr__(self):
    return str(self)


def _process_args_kwargs(curr_frame, args, kwargs):
  processed_args = [arg.evaluate(curr_frame) for arg in args]
  processed_kwargs = {
      name: value.evaluate(curr_frame) for name, value in kwargs.items()
  }
  return processed_args, processed_kwargs


NATIVE_TYPES = (int, str, list, dict, type(None))


@attr.s(str=False, repr=False)
class NativeObject(PObject):
  '''NativeObject wraps native-Python objects.

  This is primarily intended for the simple types listed in NATIVE_TYPES, however, it can also wrap
  arbitrary Python objects and performs a best-effort attempt at wrapping their API.
  
  This is particularly useful for native modules for which we don't have have raw python source
  and thus cannot create our Module instances. Instead, these modules can be loaded as
  NativeObjects and be run in relative isolation.'''
  _native_object = attr.ib()
  _dynamic_container = attr.ib(factory=DynamicContainer)

  def has_attribute(self, name):
    return hasattr(self._native_object,
                   name) or self._dynamic_container.has_attribute(name)

  def get_attribute(self, name):
    try:
      native_object = getattr(self._native_object, name)
      if isinstance(native_object, NATIVE_TYPES):
        return NativeObject(native_object)
      elif isinstance(native_object, PObject):
        return native_object
      elif isinstance(native_object, types.FunctionType):
        pass  # TODO.
    except AttributeError as e:  # E.g. <str>.get_attribute
      # TODO: Support for some native objects - str, int, list perhaps.
      debug(f'Failed to access {name} from {self._native_object}. {e}')
    return self._dynamic_container.get_attribute(name)

  def set_attribute(self, name, value):
    self._dynamic_container.set_attribute(name, value)

  def apply_to_values(self, func):
    func(self._native_object)

  def value_equals(self, other) -> FuzzyBoolean:
    try:
      value = other.value()
      if value == self.value:
        return FuzzyBoolean.TRUE
    except AmbiguousFuzzyValueDoesntHaveSingleValueError:
      return FuzzyBoolean.MAYBE  # TODO
    return FuzzyBoolean.FALSE

  def value_is_a(self, type_) -> FuzzyBoolean:
    return FuzzyBoolean.TRUE if isinstance(self._native_object,
                                           type_) else FuzzyBoolean.FALSE

  def value(self) -> object:
    return self._native_object

  def bool_value(self) -> FuzzyBoolean:
    return FuzzyBoolean.TRUE if self._native_object else FuzzyBoolean.FALSE

  def call(self, curr_frame, args, kwargs):
    args, kwargs = _process_args_kwargs(curr_frame, args, kwargs)
    try:
      arg_values = [arg.value() for arg in args]
      kwarg_values = {name: value.value() for name, value in kwargs.items()}
    except AmbiguousFuzzyValueDoesntHaveSingleValueError as e:
      debug(e)
    else:
      try:
        return NativeObject(
            self._native_object.__call__(*arg_values, **kwarg_values))
      except Exception as e:
        warning(e)

    return UnknownObject(f'Call on {type(self._native_object)}')

  def get_item_pobject_index(self, indicies):
    try:
      index = indicies.value()
    except AmbiguousFuzzyValueDoesntHaveSingleValueError:
      return UnknownObject(f'{self._native_object}[{indicies}]')
    try:
      value = self._native_object.__getitem__(index)
    except (TypeError, KeyError, IndexError, AttributeError,
            AmbiguousFuzzyValueDoesntHaveSingleValueError):
      return UnknownObject(f'{self._native_object}[{indicies}]')
    except Exception as e:
      import traceback
      traceback.print_tb(e.__traceback__)
      error(e)
    else:
      if isinstance(value, PObject):
        return value
      return pobject_from_object(value)
    return UnknownObject(f'{self._native_object}[{indicies}]')

  def get_item(self, curr_frame, index_expression):
    return self.get_item_pobject_index(index_expression.evaluate(curr_frame))

  def set_item(self, curr_frame, index, value):
    # TODO: item_dynamic_container?
    if hasattr(self._native_object, '__setitem__'):
      try:
        self._native_object.__setitem__(
            index.evaluate(curr_frame).value(),
            value.evaluate(curr_frame).value())
      except (KeyError, AmbiguousFuzzyValueDoesntHaveSingleValueError):
        pass
      except Exception as e:
        error(f'While setting {self._native_object}[{index}] = {value}')
        error(e)

  def to_dict(self):
    if hasattr(self._native_object, '__dict__'):
      items_iter = self._native_object.__dict__.items()
    elif isinstance(self._native_object, Dict):
      items_iter = self._native_object.items()
    elif hasattr(self._native_object, '__slots__'):

      def iterator():
        for name in self._native_object.__slots__:
          try:
            yield name, getattr(self._native_object, name)
          except AttributeError:
            pass

      items_iter = iterator()
    else:
      debug(f'{self._native_object} can\'t be used as dict.')
      return {}
    return {name: pobject_from_object(value) for name, value in items_iter}

  def iterator(self):
    if hasattr(self._native_object, '__iter__'):
      try:
        iterator = self._native_object.__iter__()

        def wrapper():
          try:
            yield pobject_from_object(next(iterator))
          except StopIteration:
            pass

        return wrapper()
      except Exception as e:
        error(e)
    return super().iterator()

  def __str__(self):
    return f'NO({self._native_object})'

  def __repr__(self):
    return str(self)


def pobject_from_object(obj):
  if isinstance(obj, NATIVE_TYPES):
    return NativeObject(obj)
  if isinstance(obj, PObject):
    return obj
  # TODO: if isinstance(obj, Namespace)
  return AugmentedObject(obj)


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
    except AttributeError as e:  # E.g. <str>.get_attribute
      # TODO: Support for some native objects - str, int, list perhaps.
      debug(f'Failed to access {name} from {self._object}')
      return self._dynamic_container.get_attribute(name)

  def set_attribute(self, name, value):
    # Can this get messy at all?
    if self._object.has_attribute(name):
      self._object.set_attribute(name, value)
    else:
      self._dynamic_container.set_attribute(name, value)

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

  def call(self, curr_frame, args, kwargs):
    if hasattr(self._object, 'call'):
      return self._object.call(curr_frame, args, kwargs)
    _process_args_kwargs(curr_frame, args, kwargs)
    return UnknownObject('Call?')

  def get_item_pobject_index(self, indicies):
    if isinstance(self._object, PObject):
      return self._object.get_item_pobject_index(indicies)
    # TODO
    return UnknownObject('')

  def get_item(self, curr_frame, index_expression):
    if isinstance(self._object, PObject):
      return self._object.get_item(index_expression)
    if self._object.has_attribute('__getitem__'):
      getitem = self._object.get_attribute('__getitem__')
      return getitem.call(curr_frame, [index_expression], {})

    # TODO?
    # self._object.get_item_pobject_index(indicies)
    return UnknownObject(f'{self._object}[{index_expression}]')

  def set_item(self, curr_frame, index_expression, value_expression):
    if isinstance(self._object, PObject):
      self._object.set_item(index_expression, value_expression)
    elif self._object.has_attribute('__setitem__'):
      getitem = self._object.get_attribute('__setitem__')
      return getitem.call(curr_frame, [index_expression, value_expression], {})
    else:
      # TODO: item_dynamic_container
      warning(
          f'Skipping setting {self._object}[{index_expression}] = {value_expression}'
      )

  def __str__(self):
    return f'AO({self._object}):[{self._dynamic_container}]'

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
        new_values.append(pobject_from_object(val))
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
      raise AmbiguousFuzzyValueDoesntHaveSingleValueError(
          f'Does not have a single value: {self._values}')
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

  def call(self, curr_frame, args, kwargs):
    out = []
    for value in self._values:
      result = value.call(curr_frame, args, kwargs)
      assert isinstance(result, PObject)
      out.append(result)
    if len(out) > 1:
      return FuzzyObject(out)
    elif out:  # len(out) == 1
      return out[0]
    raise EmptyFuzzyValueError()

  def get_item_pobject_index(self, indicies):
    # TODO: This gets mucky bc we need expressions for making function calls and can't create
    # expressions...
    out = []
    for value in self._values:
      out.append(value.get_item_pobject_index(
          indicies))  # TODO: Add API get_item_processed_args
    if len(out) > 1:
      return FuzzyObject(out)
    elif out:  # len(out) == 1
      return out[0]
    return UnknownObject(f'FV[{indicies}]')

  def _get_item_internal(self, curr_frame, index_expression, indicies):
    out = []
    for value in self._values:
      try:
        if isinstance(value, FuzzyObject):
          result = value._get_item_internal(curr_frame, index_expression,
                                            indicies)
        elif hasattr(value, 'get_item_pobject_index'):
          result = value.get_item_pobject_index(indicies)
        else:  # Default.
          result = value.get_item(index_expression)
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

  def get_item(self, curr_frame, index_expression):
    indicies = index_expression.evaluate(curr_frame)
    return self._get_item_internal(curr_frame, index_expression, indicies)

  def set_item(self, curr_frame, index, value):
    debug(f'Skipping setting FV[{index}] = {value}')

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

NONE_POBJECT = NativeObject(None)
# UNKNOWN_POBJECT = FuzzyObject()
