import collections
from abc import ABC, abstractmethod
from enum import Enum
from functools import partial, wraps
from typing import List

import attr

from . import collector, serialization
from ...nsn_logging import debug, error, info, warning
from .errors import (AmbiguousFuzzyValueError, LoadingModuleAttributeError,
                     SourceAttributeError)
from .utils import to_dict_iter

_OPERATORS = [
    '__add__', '__and__', '__ge__', '__gt__', '__le__', '__lt__', '__lshift__', '__mod__', '__mul__',
    '__ne__', '__or__', '__pow__', '__radd__', '__rand__', '__rdivmod__', '__rfloordiv__', '__rlshift__',
    '__rmod__', '__rmul__', '__sub__', '__truediv__', '__xor__'
]


class LanguageObject:
  ...


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
    return FuzzyBoolean.MAYBE if self.maybe_true() and other.maybe_true() else FuzzyBoolean.FALSE

  def or_expr(self, other):
    assert isinstance(other, FuzzyBoolean)
    # if hasattr(other, bool_value):
    if self == FuzzyBoolean.FALSE and other == FuzzyBoolean.FALSE:
      return FuzzyBoolean.FALSE
    elif self == FuzzyBoolean.TRUE or other == FuzzyBoolean.TRUE:
      return FuzzyBoolean.TRUE
    return FuzzyBoolean.MAYBE if self.maybe_true() or other.maybe_true() else FuzzyBoolean.FALSE

  def maybe_true(self):
    return self == FuzzyBoolean.MAYBE or self == FuzzyBoolean.TRUE

  def to_pobject(self):
    if self == FuzzyBoolean.TRUE:
      return NativeObject(True)
    if self == FuzzyBoolean.FALSE:
      return NativeObject(False)
    return FuzzyObject([NativeObject(True), NativeObject(False)])

  def serialize(self, **kwargs):
    return FuzzyBoolean.__qualname__, self.value


class PObjectType(Enum):
  NORMAL = 0
  STARRED = 1  # *args
  DOUBLE_STARRED = 2  # **kwargs


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
  pobject_type = PObjectType.NORMAL
  imported = False

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

  # @abstractmethod
  # def value_equals(self, other) -> FuzzyBoolean:
  #   ...

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
  def get_item(self, curr_frame, index_pobject):
    ...

  @abstractmethod
  def set_item(self, curr_frame, index_pobject, value_pobject):
    ...

  def invert(self):
    return self.bool_value().invert().to_pobject()

  def and_expr(self, other):
    # Don't care about shortcircuiting.
    if isinstance(other, LazyObject):
      return other.and_expr(self)
    return self.bool_value().and_expr(other.bool_value()).to_pobject()

  def or_expr(self, other):
    # Don't care about shortcircuiting.
    if isinstance(other, LazyObject):
      return other.or_expr(self)
    return self.bool_value().or_expr(other.bool_value()).to_pobject()

  def iterator(self):
    return iter([])

  def hash_value(self):
    return hash(self.value())

  def to_dict(self):
    '''Stand-in for __dict__.'''
    raise NoDictImplementationError()
    # assert False, 'Not Implemented.'  # Don't want to be caught by normal NotImplementedError logic..

  def update_dict(self, pobject):
    raise NotImplementedError()

  def __bool__(self):
    raise ValueError('Dangerous use of PObject - just use is None or bool_value() to avoid ambiguity.')


@attr.s(str=False, repr=False, slots=True)
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

  def items(self):
    return self.attributes.items()

  def __str__(self):
    return f'{list(self.attributes.keys())}'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False, slots=True)
class UnknownObject(PObject):
  name = attr.ib()  # For recording source of value - e.g. functools.wraps.
  imported = attr.ib(False)
  _dynamic_container = attr.ib(init=False, factory=DynamicContainer)

  def has_attribute(self, name):
    return self._dynamic_container.has_attribute(name)

  def get_attribute(self, name):
    return self._dynamic_container.get_attribute(name)

  def set_attribute(self, name, value):
    self._dynamic_container.set_attribute(name, value)

  def apply_to_values(self, func):
    func(self)

  # def value_equals(self, other) -> FuzzyBoolean:
  #   return FuzzyBoolean.TRUE if self == other else FuzzyBoolean.MAYBE

  def value_is_a(self, type_) -> FuzzyBoolean:
    return FuzzyBoolean.MAYBE

  # TODO: Rename 'dereference'?
  def value(self) -> object:
    return None

  def bool_value(self) -> FuzzyBoolean:
    return FuzzyBoolean.MAYBE

  def call(self, curr_frame, args, kwargs):
    return UnknownObject('Call?')

  def get_item(self, curr_frame, index_pobject):
    # TODO
    return UnknownObject('get_item?')

  def set_item(self, curr_frame, index_pobject, value_pobject):
    ...

  def __str__(self):
    return f'UO({self._dynamic_container})'

  def __repr__(self):
    return str(self)


NATIVE_TYPES = (int, float, str, list, dict, type(None))


@attr.s(str=False, repr=False, slots=True)
class NativeObject(PObject):
  '''NativeObject wraps native-Python objects.

  This is primarily intended for the simple types listed in NATIVE_TYPES, however, it can also wrap
  arbitrary Python objects and performs a best-effort attempt at wrapping their API.

  This is particularly useful for native modules for which we don't have have raw python source
  and thus cannot create our Module instances. Instead, these modules can be loaded as
  NativeObjects and be run in relative isolation.'''
  _native_object = attr.ib()
  _read_only = attr.ib(False)
  imported = attr.ib(False)
  _dynamic_container = attr.ib(init=False, factory=DynamicContainer)

  def has_attribute(self, name):
    return hasattr(self._native_object, name) or self._dynamic_container.has_attribute(name)

  def get_attribute(self, name):
    try:
      native_object = getattr(self._native_object, name)
    except AttributeError as e:  # E.g. <str>.get_attribute
      # TODO: Support for some native objects - str, int, list perhaps.
      debug(f'Failed to access {name} from {self._native_object}. {e}')
    else:
      return pobject_from_object(native_object, self._read_only)
    return self._dynamic_container.get_attribute(name)

  def set_attribute(self, name, value):
    self._dynamic_container.set_attribute(name, value)

  def apply_to_values(self, func):
    func(self._native_object)

  # def value_equals(self, other) -> FuzzyBoolean:
  #   try:
  #     value = other.value()
  #     if value == self.value:
  #       return FuzzyBoolean.TRUE
  #   except AmbiguousFuzzyValueError:
  #     return FuzzyBoolean.MAYBE  # TODO
  #   return FuzzyBoolean.FALSE

  def value_is_a(self, type_) -> FuzzyBoolean:
    return FuzzyBoolean.TRUE if isinstance(self._native_object, type_) else FuzzyBoolean.FALSE

  def value(self) -> object:
    return self._native_object

  def bool_value(self) -> FuzzyBoolean:
    return FuzzyBoolean.TRUE if self._native_object else FuzzyBoolean.FALSE

  def call(self, curr_frame, args, kwargs):
    # try:
    #   arg_values = [arg.value() for arg in args]
    #   kwarg_values = {name: value.value() for name, value in kwargs.items()}
    # except AmbiguousFuzzyValueError as e:
    #   debug(e)
    # else:
    # try:
    #   # TODO: Add whitelist.
    #   # return NativeObject(self._native_object.__call__(*arg_values, **kwarg_values))
    # except Exception as e:
    #   warning(e)

    return UnknownObject(f'Call on {type(self._native_object)}')

  def get_item(self, curr_frame, index_pobject):
    try:
      index = index_pobject.value()
    except AmbiguousFuzzyValueError:
      return UnknownObject(f'{self._native_object}[{index_pobject}]')
    try:
      value = self._native_object.__getitem__(index)
    except (TypeError, KeyError, IndexError, AttributeError):
      return UnknownObject(f'{self._native_object}[{index_pobject}]')
    else:
      if isinstance(value, PObject):
        if isinstance(value, NativeObject):
          value._read_only = self._read_only
        return value
      return pobject_from_object(value, read_only=self._read_only)
    return UnknownObject(f'{self._native_object}[{index_pobject}]')

  def set_item(self, curr_frame, index, value):
    if self._read_only:
      debug(f'Cannot set {index} on read-only NO.')
      return

    # TODO: item_dynamic_container?
    if hasattr(self._native_object, '__setitem__'):
      try:
        self._native_object.__setitem__(index.value(), value.value())
      except (KeyError, AmbiguousFuzzyValueError):
        pass
      except Exception as e:
        error(f'While setting {self._native_object}[{index}] = {value}')
        error(e)

  def to_dict(self):
    items_iter = to_dict_iter(self._native_object)
    return {name: pobject_from_object(value, read_only=self._read_only) for name, value in items_iter}

  def update_dict(self, pobject):
    if self._read_only:
      warning(f'Cannot update dictionary of read-only native object')
      return

    if isinstance(pobject, LazyObject):
      pobject = pobject._load_and_ret()
    if isinstance(pobject, NativeObject) and isinstance(pobject._native_object, dict) and isinstance(
        self._native_object, dict):
      self._native_object.update(pobject._native_object)
      return
    raise NotImplementedError()

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

  def serialize(self, **kwargs):
    if isinstance(self._native_object, NATIVE_TYPES):
      return NativeObject.__qualname__, serialization.serialize(self._native_object, **kwargs)
    # TODO: return native_conversion_func, object.path'
    if hasattr(self._native_object, '__module__'):
      return UnknownObject(f'{self._native_object.__module__}.{self._native_object.__class__.__qualname__}')
    if hasattr(self._native_object, '__name__'):
      return UnknownObject(self._native_object.__name__)
    return UnknownObject(str(self._native_object))

  def __str__(self):
    return f'NO({self._native_object})'

  def __repr__(self):
    return str(self)


def pobject_from_object(obj, read_only=False):
  if isinstance(obj, LanguageObject):
    return AugmentedObject(obj)
  if isinstance(obj, PObject):
    return obj
  if isinstance(obj, FuzzyBoolean):
    return obj.to_pobject()

  return NativeObject(obj, read_only=read_only)


class LazyObjectLoadingError(Exception):
  ...


def _passthrough_if_loaded(func):
  @wraps(func)
  def wrapper(self, *args, **kwargs):
    if self._loaded_object is not None:
      return getattr(self._loaded_object, func.__name__)(*args, **kwargs)
    return func(self, *args, **kwargs)

  return wrapper


_lazy_object_loading_dict = collections.OrderedDict()


@attr.s
class LazyInfiniteLoopContext:
  function = attr.ib()
  lazy_object = attr.ib()

  def __enter__(self):
    _lazy_object_loading_dict[(self.function, id(self.lazy_object))] = self.lazy_object.name

  def __exit__(self, exc_type, exc_value, traceback):
    del _lazy_object_loading_dict[(self.function, id(self.lazy_object))]


def loop_checker(func):
  @wraps(func)
  def wrapper(self, *args, **kwargs):
    if (func, id(self)) in _lazy_object_loading_dict:
      error(f'Infinite loop while loading lazy objects - either source error or error in our code.')
      info(f'_lazy_object_loading_dict: {_lazy_object_loading_dict}')
      info(f'collector._filename_context: {collector._filename_context}')
      assert False
    with LazyInfiniteLoopContext(func, self):
      out = func(self, *args, **kwargs)
    return out

  return wrapper


@attr.s(str=False, repr=False, slots=True)
class LazyObject(PObject):
  name = attr.ib()
  _loader = attr.ib()
  imported = attr.ib(False)
  _loader_filecontext = attr.ib(None, init=False)
  _loaded_object = attr.ib(init=False, default=None)
  # _loaded = attr.ib(init=False, default=False)
  _loading = attr.ib(init=False, default=False)
  _loading_failed = attr.ib(init=False, default=False)
  _dynamic_container = attr.ib(init=False, factory=DynamicContainer)
  _deferred_operations = attr.ib(init=False, factory=list)
  _deferred_funcs = attr.ib(init=False, factory=list)

  def __attrs_post_init__(self):
    self._loader_filecontext = collector._filename_context[-1]

  # @loop_checker
  def _load(self):
    if self._loaded_object is not None or self._loading_failed or self._loading:
      return

    self._loading = True
    try:
      with collector.FileContext(self._loader_filecontext):
        self._loaded_object = self._loader()
    except OSError as e:  # Exception
      error(f'Unable to lazily load {self.name}')
      import traceback
      traceback.print_tb(e.__traceback__)
      print(e)
      raise e
    else:
      assert isinstance(self._loaded_object, PObject)
      # assert not isinstance(self._loaded_object, LazyObject)
    finally:
      self._loading_failed = self._loaded_object is None
      if self._loading_failed:
        warning(f'Failed to load lazy object!')
        self._loaded_object = UnknownObject(self.name)
      self._apply_deferred_to_loaded()
      self._loading = False

  def _apply_deferred_to_loaded(self):
    # Okay, this is a touch questionable it feels like since theoretically, ordering of events
    # *could* matter?
    for name, value in self._dynamic_container.items():
      self._loaded_object.set_attribute(name, value)

    for operation in self._deferred_operations:
      operation()

    for func in self._deferred_funcs:
      self._loaded_object.apply_to_values(func)

  def has_attribute(self, name) -> bool:
    return self._load_and_ret().has_attribute(name)

  def _load_and_ret(self) -> PObject:
    self._load()
    return self._loaded_object

  @_passthrough_if_loaded
  def get_attribute(self, name):
    self._load()
    return LazyObject(f'{self.name}.{name}', lambda: self._loaded_object.get_attribute(name))

  @_passthrough_if_loaded
  def set_attribute(self, name, value):
    self._dynamic_container.set_attribute(name, value)

  @_passthrough_if_loaded
  def apply_to_values(self, func):
    self._deferred_funcs.append(func)

  # def value_equals(self, other) -> FuzzyBoolean:
  #   if isinstance(other, LazyObject):
  #     return FuzzyBoolean.TRUE if self == other else FuzzyBoolean.MAYBE
  #   else:

  @loop_checker
  def value_is_a(self, type_) -> FuzzyBoolean:
    self._load()
    return self._loaded_object.value_is_a(type_)

  # TODO: Rename 'dereference'?
  @loop_checker
  def value(self) -> object:
    self._load()
    return self._loaded_object.value()

  @loop_checker
  def bool_value(self) -> FuzzyBoolean:
    return self._load_and_ret().bool_value()

  @_passthrough_if_loaded
  def invert(self):
    return LazyObject(f'not {self.name}', lambda: self.bool_value().invert().to_pobject())

  @_passthrough_if_loaded
  def and_expr(self, other):
    # Don't care about shortcircuiting.
    return LazyObject(
        f'{self.name} and {other}', lambda: self.bool_value().and_expr(other.bool_value()).to_pobject())

  @_passthrough_if_loaded
  def or_expr(self, other):
    # Don't care about shortcircuiting.
    return LazyObject(
        f'{self.name} and {other}', lambda: self.bool_value().or_expr(other.bool_value()).to_pobject())

  @_passthrough_if_loaded
  def call(self, curr_frame, args, kwargs):
    # We have to do a snapshot here because the call is delayed - we want to do the function call at the
    # delayed time as if the Frame was as it is now. This does *not* snapshot PObject states.
    # TODO: Consider somehow snapshotting PObjects too.
    frame = curr_frame.snapshot()
    return LazyObject(f'{self.name}({_pretty(args)},{_pretty(kwargs)})',
                      partial(lambda a, b, c, : self._load_and_ret().call(a, b, c), frame, args, kwargs))

  @_passthrough_if_loaded
  def get_item(self, curr_frame, index_pobject, deferred_value=False):
    # We have to do a snapshot here because the call is delayed - we want to do the function call at the
    # delayed time as if the Frame was as it is now. This does *not* snapshot PObject states.
    frame = curr_frame.snapshot()
    # TODO: Drop this deferred_value nonsense?
    return LazyObject(
        f'{self.name}[{index_pobject}]', lambda: self._load_and_ret().get_item(
            frame,
            index_pobject.value() if deferred_value else index_pobject))

  @_passthrough_if_loaded
  def set_item(self, curr_frame, index_pobject, value_pobject, deferred_value=False):
    # We have to do a snapshot here because the call is delayed - we want to do the function call at the
    # delayed time as if the Frame was as it is now. This does *not* snapshot PObject states.
    frame = curr_frame.snapshot()

    def _set_item():
      self._load_and_ret().set_item(frame,
                                    index_pobject.value() if deferred_value else index_pobject,
                                    value_pobject.value() if deferred_value else value_pobject)

    self._deferred_operations.append(_set_item)

  @_passthrough_if_loaded
  def update_dict(self, pobject):
    if isinstance(pobject, (NativeObject, LazyObject)):
      self._deferred_operations.append(lambda: self._load_and_ret().update_dict(pobject))
      # self._loaded = True
      # self._apply_deferred_to_loaded()
    warning(f'Cannot do update_dict w/{pobject}.')

  def __str__(self):
    if self._loaded_object is not None:
      return f'LO({self._loaded_object})'
    return f'LO({self.name})'

  def __repr__(self):
    return str(self)


def _pretty(obj):
  if isinstance(obj, (dict, list, tuple)):
    return str(obj)[1:-1]  # Strip off brackets and parens.


@attr.s(str=False, repr=False, slots=True)
class AugmentedObject(PObject):  # TODO: CallableInterface
  _object = attr.ib()
  imported = attr.ib(False)
  _dynamic_container = attr.ib(init=False, factory=DynamicContainer)

  def __attrs_post_init__(self):
    assert self._object is not None

  def has_attribute(self, name):
    return self._object.has_attribute(name) or self._dynamic_container.has_attribute(name)

  def get_attribute(self, name):
    try:
      return self._object.get_attribute(name)
    except (SourceAttributeError, LoadingModuleAttributeError):
      # TODO: Log
      debug(f'Failed to access {name} from {self._object}')
    except AttributeError:
      raise
    return self._dynamic_container.get_attribute(name)

  def set_attribute(self, name, value):
    # Can this get messy at all?
    if self._object.has_attribute(name):
      self._object.set_attribute(name, value)
    else:
      self._dynamic_container.set_attribute(name, value)

  def apply_to_values(self, func):
    func(self._object)

  # def value_equals(self, other) -> FuzzyBoolean:
  #   if isinstance(other, PObject):
  #     return other.value_equals(self._object)
  #   return FuzzyBoolean.TRUE if self._object == other else FuzzyBoolean.FALSE

  def value_is_a(self, type_) -> FuzzyBoolean:
    return FuzzyBoolean.TRUE if isinstance(self._object, type_) else FuzzyBoolean.FALSE

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
    return UnknownObject('Call?')

  def get_item(self, curr_frame, index_pobject):
    if isinstance(self._object, PObject):
      return self._object.get_item(curr_frame, index_pobject)
    if self._object.has_attribute('__getitem__'):
      getitem = self._object.get_attribute('__getitem__')
      return getitem.call(curr_frame, [index_pobject], {})

    # TODO?
    return UnknownObject(f'{self._object}[{index_pobject}]')

  def set_item(self, curr_frame, index_pobject, value_pobject):
    if isinstance(self._object, PObject):
      self._object.set_item(curr_frame, index_pobject, value_pobject)
    elif self._object.has_attribute('__setitem__'):
      getitem = self._object.get_attribute('__setitem__')
      return getitem.call(curr_frame, [index_pobject, value_pobject], {})
    else:
      # TODO: item_dynamic_container
      warning(f'Skipping setting {self._object}[{index_pobject}] = {value_pobject}')

  def serialize(self, **kwargs):
    return serialization.serialize(self._object, **kwargs)

  def __str__(self):
    return f'AO({self._object})DC({self._dynamic_container})'

  def __repr__(self):
    return str(self)


class EmptyFuzzyValueError(Exception):
  ...


@attr.s(str=False, repr=False, slots=True)
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
  imported = attr.ib(False)

  @_values.validator
  def _values_valid(self, attribute, values):
    assert all(isinstance(value, PObject) for value in values)

  def __attrs_post_init(self):
    # new_values = []
    # for val in self._values:
    #   # Flatten FuzzyObjects?
    #   if isinstance(val, FuzzyObject):
    #     new_values += val._values
    #   else:
    #     new_values.append(val)
    # self._values = new_values
    self.validate()

  def validate(self):
    assert all(isinstance(value, PObject) for value in self._values)

  def __str__(self):
    return f'FV({self._values})'

  def __repr__(self):
    return str(self)

  def merge(self, other: 'FuzzyObject'):
    # dvs = list(filter(lambda x: x is not None, [self._dynamic_container, other._dynamic_container]))
    return FuzzyObject(self._values + other._values)

  def has_single_value(self):
    return len(self._values) == 1

  def value(self) -> object:
    if not self.has_single_value():
      raise AmbiguousFuzzyValueError(f'Does not have a single value: {self._values}')
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

  def set_attribute(self, name: str, value):
    if not isinstance(value, PObject):
      value = pobject_from_object(value)
    for val in self._values:
      val.set_attribute(name, value)

  def apply_to_values(self, func):
    for value in self._values:
      value.apply_to_values(func)

  # def value_equals(self, other) -> FuzzyBoolean:
  #   truths = [value.value_equals(other) for value in self._values]
  #   if all(truth == FuzzyBoolean.TRUE for truth in truths):
  #     return FuzzyBoolean.TRUE
  #   elif any(truth == FuzzyBoolean.TRUE or truth == FuzzyBoolean.MAYBE
  #            for truth in truths):
  #     return FuzzyBoolean.MAYBE
  #   return FuzzyBoolean.FALSE

  def value_is_a(self, type_) -> FuzzyBoolean:
    truths = [value.value_is_a(type_) for value in self._values]
    if all(truth == FuzzyBoolean.TRUE for truth in truths):
      return FuzzyBoolean.TRUE
    elif any(truth == FuzzyBoolean.TRUE or truth == FuzzyBoolean.MAYBE for truth in truths):
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

  def get_item(self, curr_frame, index_pobject):
    out = []
    for value in self._values:
      result = value.get_item(curr_frame, index_pobject)
      assert isinstance(result, PObject)
      out.append(result)  # TODO: Add API get_item_processed_args
    if len(out) > 1:
      return FuzzyObject(out)
    elif out:  # len(out) == 1
      return out[0]
    return UnknownObject(f'FV[{index_pobject}]')

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

  def serialize(self, **kwargs):
    return FuzzyObject.__qualname__, [serialization.serialize(value, **kwargs) for value in self._values]


# Add various operators too FuzzyObject class.
# for operator_str in _OPERATORS:
#   setattr(FuzzyObject, operator_str,
#           partialmethod(FuzzyObject._operator, operator=operator_str))

NONE_POBJECT = NativeObject(None)
# UNKNOWN_POBJECT = FuzzyObject()
