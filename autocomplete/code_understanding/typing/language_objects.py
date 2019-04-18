'''This module contains the core language abstractions used in Python that we care about modeling.

In general, these are "heavy" abstractions meaning they carry a lot of data potentially in them
which makes them less practical for exporting. We essentially want stubs for exports.

The fact that this is python wrapping python adds some complexity to things. Namely, things like
subscripting, getting/setting attributes, or calling with objects could refer to the object
being represented (e.g. the 'foo' Function in the source we're analyzing) or refer to the pythonic
operation on the abstraction itself (e.g. Function, Klass, FuzzyObject). 

In general, we work around this by using non-dunder methods that match the dunder equivalents.
So __getitem__, __getattribute__, __call__, etc. translate into get_item, get_attribute, call.
'''
from abc import ABC, abstractmethod
from copy import copy
from enum import Enum

import attr

from autocomplete.code_understanding.typing import debug
from autocomplete.code_understanding.typing.expressions import LiteralExpression, VariableExpression
from autocomplete.code_understanding.typing.frame import Frame, FrameType
from autocomplete.code_understanding.typing.pobjects import (
    NONE_POBJECT, AugmentedObject, FuzzyBoolean, UnknownObject)
from autocomplete.nsn_logging import info

# from autocomplete.nsn_logging import info


@attr.s
class Namespace:
  '''A Namespace is a container for named objects.

  Not to be confused with namespaces in the context of other languages, although same idea.
  
  This is rather similar to the model used in CPython itself in which namespaces are implemented
  with dicts.

  https://docs.python.org/3/reference/executionmodel.html#naming-and-binding
  https://tech.blog.aknin.name/2010/06/05/pythons-innards-naming/
  '''
  name: str = attr.ib()
  # We wrap a dict explicitly rather than subclassing to avoid certain odd behavior - e.g. __bool__
  # being overridden s.t. if there are no members, it will return false.
  _d = attr.ib(init=False, factory=dict)

  def __contains__(self, name):
    return name in self._d

  def __getitem__(self, name):
    return self._d[name]

  def __setitem__(self, name, value):
    self._d[name] = value

  def items(self):
    return self._d.items()

  # TODO: delete these?
  def has_attribute(self, name):
    return name in self._d

  def get_attribute(self, name):
    try:
      return self._d[name]
    except KeyError as e:
      raise AttributeError(e)

  def set_attribute(self, name, value):
    self._d[name] = value


class ModuleType(Enum):
  SYSTEM = 0
  PUBLIC = 1
  LOCAL = 2
  UNKNOWN = 3


@attr.s(str=False, repr=False)
class Module(Namespace):
  module_type: ModuleType = attr.ib()
  members = attr.ib()
  containing_package = attr.ib(None)
  filepath = attr.ib(None)

  def __attrs_post_init__(self):
    if self.module_type == ModuleType.UNKNOWN:
      self.dynamic_creation_func = lambda name: UnknownObject(name='.'.join([self.path(), name]))

  def path(self):
    return f'{self.containing_package.path()}.{self.name}' if self.containing_package else self.name

  def root(self):
    if self.containing_package:
      return self.containing_package.root()
    return self


# class CallableInterface(ABC):
#   @abstractmethod
#   def call(self, args, kwargs, args, kwargs, curr_frame): ...

#   @abstractmethod
#   def get_parameters(self): ...


@attr.s(str=False, repr=False)
class Klass(Namespace):

  def __str__(self):
    return f'class {self.name}: {list(self._d.keys())}'

  def __repr__(self):
    return str(self)

  def call(self, args, kwargs, curr_frame):
    return AugmentedObject(self.new(args, kwargs, curr_frame))

  def new(self, args, kwargs, curr_frame):
    # TODO: Handle params.
    # TODO: __init__
    instance = Instance(self)
    pobject = AugmentedObject(instance)
    for name, member in self.items():
      if member.value_is_a(
          Function
      ) == FuzzyBoolean.TRUE:  # and value.type == FunctionType.UNBOUND_INSTANCE_METHOD:
        value = member.value(
        )  # TODO: This can raise an exception for FuzzyObjects
        new_func = copy(value)
        bound_frame = new_func.get_or_create_bound_frame()
        try:
          self_param = new_func.parameters.pop(0)
          # info(f'self_param: {self_param}')
          bound_frame._locals[self_param.name] = pobject
        except IndexError:
          ...
          # info(f'No self param in {new_func}')
        new_func.type = FunctionType.BOUND_INSTANCE_METHOD
        instance[name] = AugmentedObject(new_func)
      else:
        instance[name] = member

    if '__init__' in instance:
      # info('Calling method __init__')
      instance['__init__'].value().call(args, kwargs, curr_frame)

    return instance

  def get_parameters(self):
    if '__init__' in self:
      return self['__init__'].get_parameters()
    return []


@attr.s(str=False, repr=False)
class Instance(Namespace):
  klass = attr.ib()
  name: str = attr.ib(None, init=False)  # Override namespace name.

  def __str__(self):
    return f'Inst {self.klass.name}: {list(self._d.keys())}'

  def __repr__(self):
    return str(self)


class FunctionType(Enum):
  FREE = 0
  CLASS_METHOD = 1
  STATIC_METHOD = 2  # Essentially, free.
  UNBOUND_INSTANCE_METHOD = 3
  BOUND_INSTANCE_METHOD = 4


@attr.s(str=False, repr=False)
class Function(Namespace):
  parameters = attr.ib()
  graph = attr.ib()
  type = attr.ib(FunctionType.FREE)
  # We use a notion of a 'bound frame' to encapsulate values which are
  # bound to this function - e.g. cls & self, nonlocals in a nested func.
  bound_frame = None

  # TODO: Cell vars.

  def get_or_create_bound_frame(self):
    if not self.bound_frame:
      self.bound_frame = Frame()
    return self.bound_frame

  def call(self, args, kwargs, curr_frame):
    new_frame = curr_frame.make_child(
        frame_type=FrameType.FUNCTION, namespace=self)
    if self.bound_frame:
      new_frame.merge(self.bound_frame)
    if debug.print_frame_in_function:
      info(f'Function frame: {new_frame}')
    self._process_args(args, kwargs, new_frame)
    self.graph.process(new_frame)

    return new_frame.get_returns()

  def _process_args(self, args, kwargs, curr_frame):
    param_iter = iter(self.parameters)
    arg_iter = iter(args)
    for arg, param in zip(arg_iter, param_iter):
      if param.type == ParameterType.SINGLE:
        curr_frame[param.name] = arg.evaluate(curr_frame)
      elif param.type == ParameterType.ARGS:
        curr_frame[param.name] = [arg.evaluate(curr_frame)
                                 ] + [a.evaluate(curr_frame) for a in arg_iter]
      else:  # KWARGS
        raise ValueError(
            f'Invalid number of positionals. {arg}: {args} fitting {self.parameters}'
        )

    kwargs_name = None
    for param in param_iter:
      if param.name in kwargs:
        curr_frame[VariableExpression(
            param.name)] = kwargs[param.name].evaluate(curr_frame)
      elif param.type == ParameterType.KWARGS:
        kwargs_name = param.name
      else:
        # Use default. If there's no assignment and no explicit default, this
        # will be NONE_POBJECT.
        curr_frame[VariableExpression(param.name)] = param.default

    if kwargs_name:  # Add remaining keywords to kwargs if there is one.
      in_dict = {}
      for key, value in kwargs:
        if key not in curr_frame:
          in_dict[key] = value
      curr_frame[kwargs_name] = AugmentedObject(in_dict)

  def __str__(self):
    return f'Func({tuple(self.parameters)})'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
class StubFunction(Namespace):
  parameters = attr.ib()
  returns = attr.ib()
  type = attr.ib(FunctionType.FREE)

  def call(self, args, kwargs, curr_frame):
    # TODO: Handle parameters?
    return self.returns

  def get_parameters(self, curr_frame):
    return self.parameters

  def __str__(self):
    return f'Func({tuple(self.parameters)})'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
class Parameter:
  name = attr.ib()
  type = attr.ib()
  default = attr.ib(LiteralExpression(None))

  def __str__(self):
    if self.type == ParameterType.SINGLE:
      prefix = ''
    elif self.type == ParameterType.ARGS:
      prefix = '*'
    else:
      prefix = '**'
    return f'{prefix}{self.name}'

  def __repr__(self):
    return str(self)


class ParameterType(Enum):
  SINGLE = 0
  ARGS = 1
  KWARGS = 2
