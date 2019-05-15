'''This module defines a Frame type and related types for simulating execution.

https://tech.blog.aknin.name/2010/07/22/pythons-innards-interpreter-stacks/'''
import itertools
from enum import Enum
from functools import wraps
from typing import Dict, List

import attr
from autocomplete.code_understanding.typing import collector, utils
from autocomplete.code_understanding.typing.errors import CellValueNotSetError
from autocomplete.code_understanding.typing.expressions import (AttributeExpression, Expression,
                                                                SubscriptExpression, VariableExpression)
from autocomplete.code_understanding.typing.pobjects import (NONE_POBJECT, AugmentedObject, FuzzyObject,
                                                             NativeObject, PObject, UnknownObject,
                                                             pobject_from_object)
from autocomplete.nsn_logging import info, warning, debug


@attr.s(slots=True)
class CellObject:
  '''Cell object's are simply wrappers over PObjects.

  These exist for variables/pobjects that are shared across multiple scopes.

  They are intended as a pretty direct mirror to the Cell Objects in Python used for the same
  purpose:
  https://docs.python.org/3.7/c-api/cell.html
  '''
  pobject: PObject = attr.ib(None)


class FrameType(Enum):
  NORMAL = 1
  KLASS = 2
  FUNCTION = 3
  EXCEPT = 4


def dereference_cell_object_returns(func):
  @wraps(func)
  def wrapper(self, *args, **kwargs):
    out = func(self, *args, **kwargs)
    if isinstance(out, CellObject):
      if not out.pobject:
        # NameError: free variable 'a' referenced before assignment in enclosing scope
        # raise CellValueNotSetError()
        return UnknownObject('CellValueNotSetError')
      return out.pobject
    return out

  return wrapper


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
  # https://github.com/alecthomas/importmagic/blob/master/importmagic/symbols.py

  # PYTHON3_BUILTINS = ['PermissionError']
  # ALL_BUILTINS = set(dir(__builtin__)) | set(GLOBALS) | set(PYTHON3_BUILTINS)

  # Symbol tables.
  _module = attr.ib()
  _locals: Dict = attr.ib(factory=dict)
  _builtins: Dict = attr.ib(None)  # TODO
  _returns: List[PObject] = attr.ib(factory=list)
  _frame_type: FrameType = attr.ib(FrameType.NORMAL)
  namespace = attr.ib(None)
  _back: 'Frame' = attr.ib(None)
  _cell_symbols = attr.ib(factory=set)

  # _root: 'Frame' = attr.ib(None)

  def __attrs_post_init__(self):
    if not self._builtins:
      self._builtins = {key: UnknownObject(key) for key in utils.get_possible_builtin_symbols()}
      # self._builtins['globals'] = NativeObject(lambda: return self._module.get_members())
      # self._builtins['locals'] = NativeObject(lambda: return self._locals)
      self._builtins['range'] = NativeObject(range)
      # TODO: nonlocal_names and global_names

    self.add_cell_symbols(self._cell_symbols)

  def add_cell_symbols(self, cell_symbols):
    self._cell_symbols = self._cell_symbols.union(cell_symbols)
    for symbol in cell_symbols:
      self[symbol] = CellObject()

  def contains_namespace_on_stack(self, namespace):
    if self.namespace == namespace:
      return True
    if self._back:
      return self._back.contains_namespace_on_stack(namespace)
    return False

  def snapshot(self):
    '''Creates a sort of snapshot / copy of the Frame at the current time.

    This is intended to enable delayed actions (which need the Frame in the state at which they were queue'd)
    and potentially debugging.

    The main issue of course is that the underlying PObjects are still mutable.
    '''
    return Frame(
        frame_type=self._frame_type,
        back=self._back.snapshot() if self._back else None,
        module=self._module,
        locals=self._locals.copy(),
        returns=self._returns.copy(),
        namespace=self.namespace,
        builtins=self._builtins,  # Constant, no need to copy.
        cell_symbols=self._cell_symbols.copy())

  def make_child(self, namespace, frame_type=FrameType.NORMAL, *, module=None, cell_symbols=None) -> 'Frame':
    # if self._frame_type == FrameType.NORMAL:
    if module is None:
      module = self._module
    if cell_symbols is None:
      cell_symbols = self._cell_symbols
    return Frame(frame_type=frame_type,
                 back=self,
                 module=module,
                 namespace=namespace,
                 builtins=self._builtins,
                 cell_symbols=cell_symbols)

  def _set_free_variable(self, name, value):
    if name in self._locals:
      existing_value = self[name]
      if isinstance(existing_value, CellObject):
        existing_value.pobject = value
        return
    self._locals[name] = value

  def __setitem__(self, variable: Expression, value: PObject):
    # https://stackoverflow.com/questions/38937721/global-frame-vs-stack-frame
    if not isinstance(value, PObject):
      value = pobject_from_object(value)  # Wrap everything in FuzzyObjects.
    # TODO: Handle nonlocal & global keyword states and cells.
    if isinstance(value, FuzzyObject):
      value.validate()

    if isinstance(variable, VariableExpression):
      self._set_free_variable(variable.name, value)
    elif isinstance(variable, str):
      self._set_free_variable(variable, value)
    elif isinstance(variable, SubscriptExpression):
      variable.set(value)
    else:
      # TODO: Move this logic into AttributeExpression like SubscriptExpression?
      assert isinstance(variable, AttributeExpression), variable
      pobject = variable.base_expression.evaluate(self)
      pobject.set_attribute(variable.attribute, value)

  def _get_current_filename(self):
    return self._module.filename

  def __delitem__(self, variable):
    if isinstance(variable, str):
      del self._locals[variable]
      return
    assert isinstance(variable, VariableExpression)
    del self._locals[variable.name]

  @dereference_cell_object_returns
  def __getitem__(self, variable: Expression, raise_error_if_missing=False, nested=False) -> PObject:

    if isinstance(variable, SubscriptExpression):
      return variable.get()
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
      path = name.split('.')
      assert len(path) >= 2
      # May raise a ValueError - recursive call.
      pobject = self[path[0]]
      for attribute_name in path[1:]:
        if raise_error_if_missing and not pobject.has_attribute(attribute_name):
          raise ValueError(f'{variable} doesn\'t exist in current context!')
        pobject = pobject.get_attribute(attribute_name)
      return pobject

    collector.add_referenced_symbol(self._get_current_filename(), name)
    # Given a.b.c, Python will take the most-local definition of a and
    # search from there.
    # TODO: This hackishly makes nested functions sorta work. FIXME. == NORMAL + cells.
    if name in self._locals:
      return self._locals[name]

    # We only want to dig into the stack up to the point of locals. If |name| isn't within any
    # frame on the backstack's locals, then we don't want to dig in. This way, if the name isn't
    # found at all, we are doing the logs from the highest-level frame as desired.
    if (not nested or self._frame_type == FrameType.NORMAL) and self._back and self._back.__contains__(
        name, True):
      return self._back.__getitem__(name, nested=True)

    if nested and raise_error_if_missing:
      raise KeyError(f'{variable} doesn\'t exist in current context!')

    if name in self._module._members:
      return self._module._members[name]

    if name in self._builtins:
      return self._builtins[name]
      # TODO: lineno, frame contents.

    if raise_error_if_missing:
      raise KeyError(f'{variable} doesn\'t exist in current context!')
    else:
      context_str = self.get_code_context_string()
      collector.add_missing_symbol(self._get_current_filename(), name, context_str)
      # Note: This can happen pretty often due to nuances in cases we don't handle. E.g. manually setting
      # globals, or sneaky conditionals (that we blow past) can cause this - so it's rather noisy and is thus
      # a debug instead of a warning.
      debug(f'At: {context_str}')
      debug(f'`{name}` doesn\'t exist in current context! Returning UnknownObject.')
      return UnknownObject(f'frame[{name}]')

  def __contains__(self, variable, nested=False):
    try:
      self.__getitem__(variable, nested=nested, raise_error_if_missing=True)
      return True
    except KeyError:
      return False

  def add_return(self, value):
    if not isinstance(value, PObject):
      value = pobject_from_object(value)
    self._returns.append(value)

  def get_returns(self):
    return FuzzyObject(self._returns) if self._returns else NONE_POBJECT

  def __str__(self):
    return f'{[self._locals, self._builtins]} + {self._root}\n'

  def __repr__(self):
    return str(self)

  def get_code_context_string(self):
    filename = self._get_current_filename()
    node = collector.get_current_parse_node()
    if node:
      code = node.get_code().strip()
      line = node.lineno
      # f-string doesn't like \n.
      code = code if '\n' not in code else code[:code.index("\n")] + '[Trimmed]'
      if filename:
        return f'File: "{filename}", line {line}, ({code})'
      return f'line {line}, ({code})'
    return filename
