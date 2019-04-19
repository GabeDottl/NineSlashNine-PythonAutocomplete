from abc import ABC, abstractmethod
from builtins import NotImplementedError
from functools import wraps

import attr

from autocomplete.code_understanding.typing import collector
from autocomplete.code_understanding.typing.errors import (
    ParsingError, assert_unexpected_parso)
from autocomplete.code_understanding.typing.expressions import (
    Expression, SubscriptExpression, VariableExpression)
from autocomplete.code_understanding.typing.frame import FrameType
from autocomplete.code_understanding.typing.language_objects import (
    Function, FunctionImpl, FunctionType, Klass, Module, Parameter)
from autocomplete.code_understanding.typing.pobjects import (
    FuzzyBoolean, FuzzyObject, UnknownObject)
from autocomplete.nsn_logging import error, info, warning

# from autocomplete.code_understanding.typing.collector import Collector


class CfgNode(ABC):
  collector: 'Collector' = None  # TODO: Drop.
  parso_node = attr.ib()

  def process(self, curr_frame):
    with collector.ParsoNodeContext(self.parso_node):
      # info(f'Processing: {collector.get_code_context_string()}')
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
  module_loader = attr.ib(kw_only=True)

  def _process_impl(self, curr_frame):
    name = self.as_name if self.as_name else self.module_path
    module = self.module_loader.get_module(self.module_path)
    # info(f'Importing {module.path()} as {name}')  # Logs *constantly*
    if self.collector:
      self.collector.add_module_import(module.path(), self.as_name)
    curr_frame[name] = module


@attr.s
class FromImportCfgNode(CfgNode):
  module_path = attr.ib()
  from_import_name = attr.ib()
  parso_node = attr.ib()
  as_name = attr.ib(None)
  module_loader = attr.ib(kw_only=True)

  def _process_impl(self, curr_frame):
    name = self.as_name if self.as_name else self.from_import_name
    module = self.module_loader.get_module(self.module_path)
    if self.collector:
      self.collector.add_from_import(module.path(), self.from_import_name,
                                     self.as_name)
    # info(f'{name} from {module.path}')  # Logs *constantly*
    if self.from_import_name == '*':
      raise NotImplementedError(
          f'Failing to handle: from {self.module_path} import * | importing nothing.'
      )
    try:
      curr_frame[name] = module.get_attribute(self.from_import_name)
    except AttributeError as e:
      warning(
          f'from_import_name {self.from_import_name} not found in {self.module_path}. {e}'
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
  right_expression: Expression = attr.ib()
  value_node = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame, strict=False):
    # TODO: Handle operator.
    result = self.right_expression.evaluate(curr_frame)
    self._process_variable(curr_frame, self.left_variables, result)

  def _process_variable(self, curr_frame, variable, result):
    if (hasattr(variable, '__len__') and len(variable) == 1):
      variable = variable[0]
    if not hasattr(variable, '__iter__'):
      if self.collector:
        self.collector.add_variable_assignment(
            variable, f'({self.value_node.get_code().strip()})')
      assert_unexpected_parso(isinstance(variable, Expression), variable)
      if isinstance(variable, SubscriptExpression):
        variable.set(curr_frame, result)
      else:
        # TODO: Handle this properly...
        curr_frame[variable] = result
    else:
      # Recursively process variables.
      for i, variable_item in enumerate(variable):
        self._process_variable(curr_frame, variable_item,
                               result._get_item_processed(i))

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
    klass._members = new_frame._locals
    for name, member in klass.items():

      def instance_member(f):
        if isinstance(f, Function):
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
    func_name = '.'.join([curr_frame._namespace.name, self.name
                         ]) if curr_frame._namespace else self.name
    func = FunctionImpl(
        name=func_name, parameters=processed_params, graph=self.suite)
    if self.collector:
      self.collector.add_function_node(func)
    curr_frame[VariableExpression(self.name)] = func

  def __str__(self):
    return f'def {self.name}({self.parameters}):\n  {self.suite}\n'


@attr.s
class ReturnCfgNode(CfgNode):
  expression: Expression = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    curr_frame.add_return(self.expression.evaluate(curr_frame))
