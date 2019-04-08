from abc import ABC
from copy import copy
from enum import Enum

import attr

from autocomplete.code_understanding.typing import debug
from autocomplete.code_understanding.typing.expressions import (LiteralExpression,
                                                                VariableExpression)
from autocomplete.code_understanding.typing.frame import Frame, FrameType
from autocomplete.code_understanding.typing.fuzzy_value import (NONE_FUZZY_VALUE,
                                                                UnknownValue,
                                                                FuzzyValue)
from autocomplete.nsn_logging import info


class FunctionType(Enum):
  FREE = 0
  CLASS_METHOD = 1
  STATIC_METHOD = 2  # Essentially, free.
  UNBOUND_INSTANCE_METHOD = 3
  BOUND_INSTANCE_METHOD = 4


@attr.s(str=False, repr=False)
class Function:
  name = attr.ib()
  parameters = attr.ib()
  graph = attr.ib()
  type = attr.ib(FunctionType.FREE)
  # We use a notion of a 'bound frame' to encapsulate values which are
  # bound to this function - e.g. cls & self, nonlocals in a nested func.
  bound_frame = None

  def get_or_create_bound_frame(self):
    if not self.bound_frame:
      self.bound_frame = Frame()
    return self.bound_frame

  def call(self, args, kwargs, curr_frame):
    new_frame = curr_frame.make_child(type=FrameType.FUNCTION, name=self.name)
    if self.bound_frame:
      new_frame.merge(self.bound_frame)
    if debug.print_frame_in_function:
      info(f'Function frame: {new_frame}')
    # TODO: Process args & kwargs, put on Frame.
    # info(f'curr_frame: {curr_frame.get_variables()}')
    self.process_args(args, kwargs, new_frame)
    self.graph.process(new_frame)
    # info(f'new_frame: {new_frame.get_variables()}')
    # info(f'curr_frame: {curr_frame.get_variables()}')

    returns = new_frame.get_returns()
    if not returns:
      return NONE_FUZZY_VALUE
    out = returns[0]
    for ret in returns[1:]:
      out = out.merge(ret)
    return out

  def process_args(self, args, kwargs, curr_frame):
    param_iter = iter(self.parameters)
    arg_iter = iter(args)
    for arg, param in zip(arg_iter, param_iter):
      if param.type == ParameterType.SINGLE:
        curr_frame[VariableExpression(param.name)] = arg.evaluate(curr_frame)
      elif param.type == ParameterType.ARGS:
        curr_frame[VariableExpression(
            param.name)] = [arg.evaluate(curr_frame)
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
        # will be NONE_FUZZY_VALUE.
        curr_frame[VariableExpression(param.name)] = param.default

    if kwargs_name:  # Add remaining keywords to kwargs if there is one.
      in_dict = {}
      for key, value in kwargs:
        if key not in curr_frame:
          in_dict[key] = value
      curr_frame[kwargs_name] = FuzzyValue([in_dict])

  def __str__(self):
    return f'Func({tuple(self.parameters)})'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
class StubFunction:
  parameters = attr.ib()
  returns = attr.ib()
  type = attr.ib(FunctionType.FREE)

  def call(self, args, kwargs, curr_frame):
    # TODO: Handle parameters?
    return self.returns

  def __str__(self):
    return f'Func({tuple(self.parameters)})'

  def __repr__(self):
    return str(self)


class Attributable(ABC):
  dynamic_creation_func = None
  members = None

  def get_attribute(self, name: str):
    if self.dynamic_creation_func and not self.has_attribute(name):
      out = self.dynamic_creation_func(name)
      self.members[name] = out
      return out
    return self.members[name]

  def set_attribute(self, name: str, value: FuzzyValue):
    self.members[name] = value

  def has_attribute(self, name):
    return name in self.members




@attr.s(str=False, repr=False)
class Klass(Attributable):
  name = attr.ib()
  members = attr.ib()

  def __str__(self):
    return f'class {self.name}: {list(self.members.keys())}'

  def __repr__(self):
    return str(self)

  def call(self, args, kwargs, curr_frame):
    return FuzzyValue([self.new(args, kwargs, curr_frame)])

  def new(self, args, kwargs, curr_frame):
    # TODO: Handle params.
    # TODO: __init__
    instance_members = {}
    instance = Instance(self, instance_members)
    fv_instance = FuzzyValue([instance])
    for name, member in self.members.items():
      if member.has_single_value() and isinstance(
          member.value(), Function) and member.value(
          ).type == FunctionType.UNBOUND_INSTANCE_METHOD:
        new_func = copy(member.value())
        bound_frame = new_func.get_or_create_bound_frame()
        self_param = new_func.parameters.pop(0)
        info(f'self_param: {self_param}')
        bound_frame.locals[self_param.name] = fv_instance
        new_func.type = FunctionType.BOUND_INSTANCE_METHOD
        instance_members[name] = FuzzyValue([new_func])
      else:
        instance_members[name] = member


    if '__init__' in instance_members:
      info('Calling method __init__')
      instance_members['__init__'].value().call(args, kwargs, curr_frame)

    return instance


@attr.s(str=False, repr=False)
class Instance(Attributable):
  klass = attr.ib()
  members = attr.ib()

  def __str__(self):
    return f'Inst {self.klass.name}: {list(self.members.keys())}'

  def __repr__(self):
    return str(self)


class ModuleType(Enum):
  SYSTEM = 0
  PUBLIC = 1
  LOCAL = 2
  UNKNOWN = 3

@attr.s(str=False, repr=False)
class Module(Attributable):
  # name = attr.ib()  # Don't need name, because that's defined by any alias in Frame.
  module_type: ModuleType = attr.ib()
  path: str = attr.ib()
  members = attr.ib()

  def __attrs_post_init__(self):
    if self.module_type == ModuleType.UNKNOWN:
      # def create_fv():
      self.dynamic_creation_func = lambda name: UnknownValue(name='.'.join([self.path, name]))

  # def __attrs_post_init__(self):
  #   self.members = copy(self.klass.members)


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
