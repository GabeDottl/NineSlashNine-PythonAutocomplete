from typing import Dict, List

from autocomplete.code_understanding.typing.classes import FuzzyValue
from autocomplete.code_understanding.typing.expressions import (AttributeExpression,
                                                                Expression,
                                                                Variable,
                                                                VariableExpression)


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
    assert isinstance(value, FuzzyValue), value
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
