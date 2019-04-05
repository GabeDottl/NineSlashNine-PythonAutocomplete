from abc import ABC
from copy import copy
from enum import Enum

import attr

from autocomplete.code_understanding.typing.classes import (NONE_FUZZY_VALUE,
                                                            FuzzyValue)
from autocomplete.code_understanding.typing.expressions import (LiteralExpression,
                                                                VariableExpression)
from autocomplete.code_understanding.typing.frame import FrameType
from autocomplete.nsn_logging import info


class FunctionType(Enum):
  FREE = 0
  CLASS_METHOD = 1
  STATIC_METHOD = 2  # Essentially, free.
  UNBOUND_INSTANCE_METHOD = 3
  BOUND_INSTANCE_METHOD = 4


@attr.s(str=False, repr=False)
class Function:
  parameters = attr.ib()
  graph = attr.ib()
  type = attr.ib(FunctionType.FREE)

  def call(self, args, kwargs, curr_frame):
    new_frame = curr_frame.make_child(type=FrameType.FUNCTION)
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

  def getattribute(self, name: str):
    return self.members[name]

  def setattribute(self, name: str, value: FuzzyValue):
    self.members[name] = value

  def hasattribute(self, name):
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
    for name, member in self.members.items():
      if member.has_single_value() and isinstance(
          member.value(), Function) and member.value(
          ).type == FunctionType.UNBOUND_INSTANCE_METHOD:
        new_func = copy(member.value())
        new_func.type = FunctionType.BOUND_INSTANCE_METHOD
        instance_members[name] = FuzzyValue([new_func])
      else:
        instance_members[name] = member

    instance = Instance(self, instance_members)
    if '__init__' in instance.members:
      info('Calling method __init__')
      instance.members['__init__'].value().call(args, kwargs, curr_frame)

    return instance


@attr.s(str=False, repr=False)
class Instance(Attributable):
  klass = attr.ib()
  members = attr.ib()

  def __str__(self):
    return f'Inst {self.klass.name}: {list(self.members.keys())}'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
class Module(Attributable):
  name = attr.ib()
  members = attr.ib()
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
