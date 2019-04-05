import traceback

import attr

from autocomplete.code_understanding.typing.classes import FuzzyValue
from autocomplete.code_understanding.typing.expressions import \
    VariableExpression
from autocomplete.code_understanding.typing.frame import FrameType
from autocomplete.code_understanding.typing.language_objects import (Function,
                                                                     Klass,
                                                                     Parameter)
from autocomplete.nsn_logging import info


class CfgNode:

  def process(self, curr_frame):
    raise NotImplementedError()  # abstract


@attr.s
class ExpressionCfgNode:
  expression = attr.ib()

  def process(self, curr_frame):
    self.expression.evaluate(curr_frame)


class NoOpCfgNode(CfgNode):

  def process(self, curr_frame):
    pass


class StmtCfgNode(CfgNode):
  # TypeError: descriptor 'statement' for 'StmtCfgNode' objects doesn't apply to 'StmtCfgNode' object
  # __slots__ = 'statement', 'next_node' # TODO Figure out why this is broken.

  def __init__(self, statement, code=''):
    self.statement = statement
    self.next_node = None
    self.code = code

  def process(self, curr_frame, strict=True):
    try:
      self.statement.evaluate(curr_frame)
    except ValueError as e:
      if not strict:
        info(f'ValueError during: {self.code}')
        # raise e
        info(f'ValueError: {e}')
        # e.tb
      else:
        info(f'self.code: {self.code}')
        raise e
    if self.next_node:
      self.next_node.process(curr_frame)

  def __str__(self):
    return self._to_str()

  def _to_str(self):
    out = []
    if self.code:
      out.append(f'{self.__class__.__name__}: {self.code}')
    if self.next_node:
      out.append(str(self.next_node))
    return '\n'.join(out)


class IfCfgNode(CfgNode):
  # __slots__ = 'expression_node_tuples'

  def __init__(self, expression_node_tuples):
    """For 'else', (True, node)"""
    self.expression_node_tuples = expression_node_tuples

  def process(self, curr_frame):
    for expression, node in self.expression_node_tuples:
      result = expression.evaluate(curr_frame)
      if result.has_single_value() and result.value():
        # Expression is definitely true - evaluate and stop here.
        node.process(curr_frame)
        break
      elif result.has_single_value() and not result.value():
        # Expression is definitely false - skip.
        continue
      else:  # Completely ambiguous.
        node.process(curr_frame)


class KlassCfgNode(CfgNode):

  def __init__(self, name, suite):
    self.name = name
    self.suite = suite

  def process(self, curr_frame):
    # Create a K
    # The members of the class shall be filled
    klass = Klass(self.name, members=None)
    curr_frame[self.name] = FuzzyValue([klass])
    new_frame = curr_frame.make_child(type=FrameType.CLASS)
    # Locals defined in this frame are actually members of our class.
    self.suite.process(new_frame)
    klass.members = new_frame.locals


class GroupCfgNode(CfgNode):

  def __init__(self, children):
    self.children = children

  def process(self, curr_frame):
    for child in self.children:
      child.process(curr_frame)

  def __str__(self):
    return '\n'.join([str(child) for child in self.children])



@attr.s
class FuncCfgNode(CfgNode):
  name = attr.ib()
  parameters = attr.ib()
  suite = attr.ib()

  def process(self, curr_frame):
    processed_params = []
    for param in self.parameters:
      if param.default is None:
        processed_params.append(param)
      else:  # Process parameter defaults at the time of definition.
        default = param.default.evaluate(curr_frame)
        processed_params.append(Parameter(param.name, param.type, default))
    curr_frame[VariableExpression(self.name)] = FuzzyValue([Function(
        processed_params, self.suite)])

  def __str__(self):
    return f'def {self.name}({self.parameters}):\n  {self.suite}\n'


@attr.s
class ReturnCfgNode(CfgNode):
  expression = attr.ib()

  def process(self, curr_frame):
    curr_frame.add_return(self.expression.evaluate(curr_frame))
