from enum import Enum
from typing import Dict, List

import attr

from autocomplete.code_understanding.typing.expressions import (AttributeExpression,
                                                                Variable,
                                                                VariableExpression)
from autocomplete.code_understanding.typing.fuzzy_value import FuzzyValue
from autocomplete.nsn_logging import info


class FrameType(Enum):
  NORMAL = 1
  CLASS = 2
  FUNCTION = 3


@attr.s(str=False, repr=False)
class Frame:
  # __slots__ = 'globals', 'locals', 'builtins'
  _globals: Dict = attr.ib(factory=dict)
  _nonlocals: Dict = attr.ib(factory=dict)
  _locals: Dict = attr.ib(factory=dict)
  builtins: Dict = attr.ib(factory=dict)  # TODO
  returns: List[FuzzyValue] = attr.ib(factory=list)
  _current_context: str = attr.ib('')
  type = attr.ib(FrameType.NORMAL)

  def merge(self, other_frame):
    self._globals.update(other_frame._globals)
    self._nonlocals.update(other_frame._nonlocals)
    self._locals.update(other_frame._locals)

  def make_child(self, type, name) -> 'Frame':
    info(f'Creating child {type}Frame from {self.type}Frame')
    if self.type == FrameType.NORMAL:
      new_frame = Frame({**self._globals, **self._locals}, type=type)
      print(new_frame)
      return new_frame
    # else: #  if self.type == FrameType.FUNCTION:
    # TODO: Function Cell vars.
    return Frame(self._globals, type=type)  # , nonlocals=self._locals)

  def __setitem__(self, variable: Variable, value: FuzzyValue):
    # assert isinstance(
    #     value, FuzzyValue), f'{id(type(value))} vs {id(FuzzyValue)}: {value}'
    if not isinstance(value, FuzzyValue):
      value = FuzzyValue([value])  # Wrap everything in FuzzyValues.
    # assert isinstance(variable, Variable), variable
    if isinstance(variable, VariableExpression):
      self._locals[variable.name] = value
    elif isinstance(variable, str):
      self._locals[variable] = value
    else:
      assert isinstance(variable, AttributeExpression), variable
      fuzzy_value = variable.base_expression.evaluate(self)
      fuzzy_value.set_attribute(variable.attribute, value)
      # if len(variable.sequence) == 2:
      #   base = self._locals[variable.sequence[0].name]
      # else:
      #   base = self.get_assignment(Variable(variable.sequence[:-1]))

      # setattr(base, variable.sequence[1], value)
    # TODO: Handle nonlocal & global keyword states.


  def __getitem__(self, variable: Variable) -> FuzzyValue:
    if isinstance(variable, AttributeExpression):
      fuzzy_value = variable.base_expression.evaluate(self)
      return fuzzy_value.get_attribute(variable.attribute)

    if isinstance(variable, str):
      name = variable
    else:
      assert isinstance(variable, VariableExpression), variable
      name = variable.name

    for group in (self._locals, self._globals, self.builtins):
      # Given a.b.c, Python will take the most-local definition of a and
      # search from there.
      if name in group:
        return group[name]
    # TODO: lineno, frame contents.
    raise ValueError(f'{variable} doesn\'t exist in current context!')

  def __contains__(self, name):
    for group in (self._locals, self._globals, self.builtins):
    # Given a.b.c, Python will take the most-local definition of a and
      # search from there.
      if name in group:
        return True

  def add_return(self, value):
    self.returns.append(value)

  def get_returns(self):
    return self.returns

  def get_variables(self):
    out = []
    for group in (self._locals, self._globals, self.builtins):
      for key in group.keys():
        out.append(key)
    return out

  def __str__(self):
    return f'{[self._locals, self._globals, self.builtins]}\n'

  def __repr__(self):
    return str(self)
