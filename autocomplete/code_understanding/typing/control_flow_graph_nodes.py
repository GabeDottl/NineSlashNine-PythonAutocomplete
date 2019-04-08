from functools import wraps

import attr

from autocomplete.code_understanding.typing import module_loader
from autocomplete.code_understanding.typing.expressions import \
    VariableExpression
from autocomplete.code_understanding.typing.frame import FrameType
from autocomplete.code_understanding.typing.fuzzy_value import (
    UnknownValue, FuzzyValue)
from autocomplete.code_understanding.typing.language_objects import (
    Function, FunctionType, Klass, Module, Parameter)
from autocomplete.nsn_logging import info


class CfgNode:

  def process(self, curr_frame):
    raise NotImplementedError()  # abstract


@attr.s
class ExpressionCfgNode:
  expression = attr.ib()
  parso_node = attr.ib()

  def process(self, curr_frame):
    self.expression.evaluate(curr_frame)


@attr.s
class ImportCfgNode(CfgNode):
  module_path = attr.ib()
  parso_node = attr.ib()
  as_name = attr.ib(None)

  def process(self, curr_frame):
    name = self.as_name if self.as_name else self.module_path
    module = module_loader.get_module(self.module_path)
    info(f'{name} in {module.path}')
    curr_frame[name] = module


@attr.s
class FromImportCfgNode(CfgNode):
  module_path = attr.ib()
  from_import_name = attr.ib()
  parso_node = attr.ib()
  as_name = attr.ib(None)

  def process(self, curr_frame):
    name = self.as_name if self.as_name else self.from_import_name
    module = module_loader.get_module(self.module_path)
    info(f'{name} from {module.path}')
    try:
      curr_frame[name] = module.get_attribute(self.from_import_name)
    except KeyError:
      info(
          f'from_import_name {self.from_import_name} not found in {self.module_path}'
      )
      curr_frame[
          name] = FuzzyValue([UnknownValue(name='.'.join([self.module_path, name]))], self)  # TODO: Extra fuzzy value / unknown?


@attr.s
class NoOpCfgNode(CfgNode):
  parso_node = attr.ib()

  def process(self, curr_frame):
    pass


@attr.s
class StmtCfgNode(CfgNode):
  statement = attr.ib()
  parso_node = attr.ib()

  def process(self, curr_frame, strict=False):
    self.statement.evaluate(curr_frame)
  
  def __str__(self):
    return self._to_str()

  def _to_str(self):
    out = []
    if self.parso_node.get_code():
      out.append(f'{self.__class__.__name__}: {self.parso_node.get_code()}')
    return '\n'.join(out)


@attr.s
class IfCfgNode(CfgNode):
  # For 'else', (True, node).
  expression_node_tuples = attr.ib()
  parso_node = attr.ib()

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


@attr.s
class KlassCfgNode(CfgNode):
  name = attr.ib()
  suite = attr.ib()
  parso_node = attr.ib()

  def process(self, curr_frame):
    klass_name = ''.join([curr_frame._current_context,self.name]) if curr_frame._current_context else self.name
    klass = Klass(klass_name, members={})
    curr_frame[self.name] = FuzzyValue([klass], self)
    new_frame = curr_frame.make_child(type=FrameType.CLASS, name=self.name)
    # Locals defined in this frame are actually members of our class.
    self.suite.process(new_frame)
    klass.members = new_frame.locals
    for name, member in klass.members.items():

      def instance_member(f):
        if isinstance(f, Function):
          info(f'Func {name} now unbound')
          f.type = FunctionType.UNBOUND_INSTANCE_METHOD

      member.apply(instance_member)


@attr.s
class GroupCfgNode(CfgNode):
  children = attr.ib()
  parso_node = attr.ib()

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
  parso_node = attr.ib()

  def process(self, curr_frame):
    processed_params = []
    for param in self.parameters:
      if param.default is None:
        processed_params.append(param)
      else:  # Process parameter defaults at the time of definition.
        default = param.default.evaluate(curr_frame)
        processed_params.append(Parameter(param.name, param.type, default))
    # Include full name.
    func_name = ''.join([curr_frame._current_context,self.name]) if curr_frame._current_context else self.name
    curr_frame[VariableExpression(self.name)] = FuzzyValue(
        [Function(func_name, parameters=processed_params, graph=self.suite)], self)

  def __str__(self):
    return f'def {self.name}({self.parameters}):\n  {self.suite}\n'


@attr.s
class ReturnCfgNode(CfgNode):
  expression = attr.ib()
  parso_node = attr.ib()

  def process(self, curr_frame):
    curr_frame.add_return(self.expression.evaluate(curr_frame))