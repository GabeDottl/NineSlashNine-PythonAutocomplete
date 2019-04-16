'''This module defines a Frame type and related types for simulating execution.

https://tech.blog.aknin.name/2010/07/22/pythons-innards-interpreter-stacks/'''
from enum import Enum
from typing import Dict, List

import attr
from autocomplete.code_understanding.typing.expressions import (
    AttributeExpression, Variable, VariableExpression)
from autocomplete.code_understanding.typing.pobjects import FuzzyObject, UnknownObject, PObject
from autocomplete.nsn_logging import info


class FrameType(Enum):
  NORMAL = 1
  KLASS = 2
  FUNCTION = 3


@attr.s(str=False, repr=False)
class Frame:
  '''Frame vaguely mirrors the Python frame for executing code.

  Like the Python frame, it has symbol tables and references the previous frame.

  The Frame touches all symbol assignments. In Python, scope blocks are constrained
  to modules, function bodies, and class definitions (control blocks such as if and while
  blocks do not effect scope).
  
  https://docs.python.org/3/reference/executionmodel.html#naming-and-binding:
  `The following constructs bind names: formal parameters to functions, import statements,
  class and function definitions (these bind the class or function name in the defining
  block), and targets that are identifiers if occurring in an assignment, for loop header,
  or after as in a with statement or except clause. The import statement of the form from
  ... import * binds all names defined in the imported module, except those beginning with
  an underscore. This form may only be used at the module level.`
  '''

  # Symbol tables.
  # _globals: Dict = attr.ib(factory=dict)  # Instead of 'globals' we use _root.locals. Falls apart with imports?
  _locals: Dict = attr.ib(factory=dict)
  _builtins: Dict = attr.ib(factory=dict)  # TODO
  # _nonlocals: Dict = attr.ib(factory=dict)
  returns: List[FuzzyObject] = attr.ib(factory=list)
  _frame_type: FrameType = attr.ib(FrameType.NORMAL)
  _back: 'Frame' = attr.ib(None)
  _root: 'Frame' = attr.ib(None)

  # TODO: nonlocal_names and global_names
  # _frame_type = attr.ib(FrameType.NORMAL)
  # TODO: Block stack?

  def merge(self, other_frame):
    # self._globals.update(other_frame._globals)
    # self._nonlocals.update(other_frame._nonlocals)
    self._locals.update(other_frame._locals)

  def make_child(self, frame_type) -> 'Frame':
    # if self._frame_type == FrameType.NORMAL:
    return Frame(frame_type=frame_type, back=self, root=self._root)

  def to_module(self) -> 'Module':
    raise NotImplementedError()

  def __setitem__(self, variable: Variable, value: FuzzyObject):
    # https://stackoverflow.com/questions/38937721/global-frame-vs-stack-frame
    if not isinstance(value, FuzzyObject):
      value = FuzzyObject([value])  # Wrap everything in FuzzyObjects.
    # TODO: Handle nonlocal & global keyword states and cells.

    if isinstance(variable, VariableExpression):
      self._locals[variable.name] = value
    elif isinstance(variable, str):
      self._locals[variable] = value
    else:
      assert isinstance(variable, AttributeExpression), variable
      pobject = variable.base_expression.evaluate(self)
      pobject.set_attribute(variable.attribute, value)

  def __getitem__(self,
                  variable: Variable,
                  raise_error_if_missing=False,
                  nested=False) -> PObject:
    if isinstance(variable, AttributeExpression):
      pobject = variable.base_expression.evaluate(self)
      return pobject.get_attribute(variable.attribute)

    if isinstance(variable, str):
      name = variable
    else:
      assert isinstance(variable, VariableExpression), variable
      name = variable.name

    # Complex case - X.b
    if '.' in name:
      index = name.find('.')
      base = name[:index]
      # May raise a ValueError - recursive call.
      pobject = self[base]
      if raise_error_if_missing and not pobject.has_attribute(name[index + 1:]):
        raise ValueError(f'{variable} doesn\'t exist in current context!')
      return pobject.get_attribute(name[index + 1:])

    # Given a.b.c, Python will take the most-local definition of a and
    # search from there.
    # TODO: This hackishly makes nested functions sorta work. FIXME. == NORMAL + cells.
    if (not nested or
        self._frame_type == FrameType.KLASS) and name in self._locals:
      return self._locals[name]
    if self._back:
      return self._back[name]
    if name in self._builtins:
      return self._builtins[name]
      # TODO: lineno, frame contents.
    info(f'{name} doesn\'t exist in current context! Returning UnknownObject.')
    if raise_error_if_missing:
      raise ValueError(f'{variable} doesn\'t exist in current context!')
    else:
      return UnknownObject(f'frame[{name}]')

  def __contains__(self, variable):
    try:
      self.__getitem__(variable, raise_error_if_missing=True)
      return True
    except ValueError:
      return False

  def add_return(self, value):
    self.returns.append(value)

  def get_returns(self):
    return self.returns

  def get_variables(self):
    out = []
    for group in (self._locals, self._globals, self._builtins):
      for key in group.keys():
        out.append(key)
    return out

  def __str__(self):
    return f'{[self._locals, self._globals, self._builtins]}\n'

  def __repr__(self):
    return str(self)
