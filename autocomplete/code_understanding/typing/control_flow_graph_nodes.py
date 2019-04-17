from abc import ABC, abstractmethod
from functools import wraps

import attr

from autocomplete.code_understanding.typing import module_loader
from autocomplete.code_understanding.typing.expressions import (
    Expression, VariableExpression)
from autocomplete.code_understanding.typing.frame import FrameType
from autocomplete.code_understanding.typing.language_objects import (
    Function, FunctionType, Klass, Module, Parameter)
from autocomplete.code_understanding.typing.pobjects import (
    FuzzyBoolean, FuzzyObject, UnknownObject)
from autocomplete.nsn_logging import info

# from autocomplete.code_understanding.typing.collector import Collector


class CfgNode(ABC):
  collector: 'Collector' = None

  def process(self, curr_frame):
    self._process_impl(curr_frame)

  @abstractmethod
  def _process_impl(self, curr_frame):
    ...


@attr.s
class ExpressionCfgNode(CfgNode):
  expression: Expression = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    self.expression.evaluate(curr_frame)


@attr.s
class ImportCfgNode(CfgNode):
  module_path = attr.ib()
  parso_node = attr.ib()
  as_name = attr.ib(None)

  def _process_impl(self, curr_frame):
    name = self.as_name if self.as_name else self.module_path
    module = module_loader.get_module(self.module_path)
    info(f'{name} in {module.path()}')
    if self.collector:
      self.collector.add_module_import(module.path(), self.as_name)
    curr_frame[name] = module


@attr.s
class FromImportCfgNode(CfgNode):
  module_path = attr.ib()
  from_import_name = attr.ib()
  parso_node = attr.ib()
  as_name = attr.ib(None)

  def _process_impl(self, curr_frame):
    name = self.as_name if self.as_name else self.from_import_name
    module = module_loader.get_module(self.module_path)
    if self.collector:
      self.collector.add_from_import(module.path(), self.from_import_name,
                                     self.as_name)
    # info(f'{name} from {module.path}')
    try:
      curr_frame[name] = module.get_attribute(self.from_import_name)
    except AttributeError:
      info(
          f'from_import_name {self.from_import_name} not found in {self.module_path}'
      )
      curr_frame[name] = UnknownObject(name='.'.join(
          [self.module_path,
           self.from_import_name]))  # TODO: Extra fuzzy value / unknown?


@attr.s
class NoOpCfgNode(CfgNode):
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    pass


@attr.s
class AssignmentStmtCfgNode(CfgNode):
  # https://docs.python.org/3/reference/simple_stmts.html#assignment-statements
  left_variables = attr.ib()
  operator = attr.ib()  # Generally equals, but possibly +=, etc.
  right_expression = attr.ib()
  value_node = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame, strict=False):
    # TODO: Handle operator.
    result = self.right_expression.evaluate(curr_frame)
    # info(f'result: {result}')
    # info(f'self.right_expression: {self.right_expression}')
    if len(self.left_variables) == 1:
      if self.collector:
        self.collector.add_variable_assignment(
            self.left_variables[0],
            self.value_node.get_code().strip())
      info(self.left_variables[0])
      curr_frame[self.left_variables[0]] = result
      # info(f'result: {result}')
      # info(
      #     f'curr_frame[self.left_variables[0]]: {curr_frame[self.left_variables[0]]}'
      # )
    else:
      for i, variable in enumerate(self.left_variables):
        if self.collector:
          self.collector.add_variable_assignment(
              variable, f'({self.value_node.get_code().strip()})[{i}]')
        # TODO: Handle this properly...
        curr_frame[variable] = result[i]

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

  def _process_impl(self, curr_frame):
    for expression, node in self.expression_node_tuples:
      result = expression.evaluate(curr_frame)
      if result.bool_value() == FuzzyBoolean.TRUE:
        # Expression is definitely true - evaluate and stop here.
        node.process(curr_frame)
        break
      elif result.bool_value() == FuzzyBoolean.FALSE:
        # Expression is definitely false - skip.
        # TODO: Process for collector.
        continue
      else:  # Completely ambiguous / MAYBE.
        node.process(curr_frame)


@attr.s
class KlassCfgNode(CfgNode):
  name = attr.ib()
  suite = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    klass_name = f'{curr_frame._namespace.name}.{self.name}' if curr_frame._namespace else self.name
    klass = Klass(klass_name)
    curr_frame[self.name] = klass
    new_frame = curr_frame.make_child(
        frame_type=FrameType.KLASS, namespace=klass)
    # Locals defined in this frame are actually members of our class.
    self.suite.process(new_frame)
    klass._d = new_frame._locals
    for name, member in klass.items():

      def instance_member(f):
        if isinstance(f, Function):
          # info(f'Func {name} now unbound')
          f.type = FunctionType.UNBOUND_INSTANCE_METHOD

      member.apply_to_values(instance_member)


@attr.s
class GroupCfgNode(CfgNode):
  children = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
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

  def _process_impl(self, curr_frame):
    processed_params = []
    for param in self.parameters:
      if param.default is None:
        processed_params.append(param)
      else:  # Process parameter defaults at the time of definition.
        default = param.default.evaluate(curr_frame)
        processed_params.append(Parameter(param.name, param.type, default))
    # Include full name.
    func_name = ''.join([curr_frame._namespace.name, self.name
                        ]) if curr_frame._namespace else self.name
    func = Function(func_name, parameters=processed_params, graph=self.suite)
    if self.collector:
      self.collector.add_function_node(func)
    curr_frame[VariableExpression(self.name)] = func

  def __str__(self):
    return f'def {self.name}({self.parameters}):\n  {self.suite}\n'


@attr.s
class ReturnCfgNode(CfgNode):
  expression = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    curr_frame.add_return(self.expression.evaluate(curr_frame))
