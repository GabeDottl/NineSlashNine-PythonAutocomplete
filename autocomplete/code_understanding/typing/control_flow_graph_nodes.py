import itertools
from abc import ABC, abstractmethod
from builtins import NotImplementedError
from functools import wraps
from typing import Iterable, List, Set, Tuple, Union

import attr

from autocomplete.code_understanding.typing import collector
from autocomplete.code_understanding.typing.errors import (
    ParsingError, assert_unexpected_parso)
from autocomplete.code_understanding.typing.expressions import (_assign_variables_to_results,
    Expression, StarExpression, SubscriptExpression, VariableExpression)
from autocomplete.code_understanding.typing.frame import Frame, FrameType
from autocomplete.code_understanding.typing.language_objects import (
    BoundFunction, Function, FunctionImpl, FunctionType, Klass, Module,
    Parameter)
from autocomplete.code_understanding.typing.pobjects import (FuzzyBoolean,
                                                             FuzzyObject,
                                                             UnknownObject)
from autocomplete.nsn_logging import error, info, warning

# from autocomplete.code_understanding.typing.collector import Collector


def instance_memoize(func):

  @wraps(func)
  def _wrapper(self):
    memoized_name = f'_{func.__name__}_memoized'
    if hasattr(self, memoized_name):
      return getattr(self, memoized_name)
    out = func(self)
    setattr(self, memoized_name, out)
    return out

  return _wrapper


class CfgNode(ABC):
  parso_node = attr.ib()

  def process(self, curr_frame):
    with collector.ParsoNodeContext(self.parso_node):
      # info(f'Processing: {collector.get_code_context_string()}')
      self._process_impl(curr_frame)

  @abstractmethod
  def _process_impl(self, curr_frame):
    ...

  @abstractmethod
  def get_non_local_symbols(self) -> Iterable[str]:
    '''Gets all symbols that are going to be nonlocal/locally defined outside this node.
    
    This does not include globals.
    '''

  @abstractmethod
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    '''Symbols that's that are both defined within this node and are visible outside of it.

    For classes and functions, these are just the names of the class/function. For other blocks,
    this will generally include all of their assignments.
    '''

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}'


@attr.s
class GroupCfgNode(CfgNode):
  children: List[CfgNode] = attr.ib(factory=list)
  parso_node = attr.ib(None)

  # Convenience
  def __getitem__(self, index) -> CfgNode:
    return self.children[index]

  # Convenience
  def __iter__(self):
    return iter(self.children)

  @children.validator
  def _validate_children(self, attribute, children):
    for child in children:
      assert isinstance(child, CfgNode)

  def _process_impl(self, curr_frame):
    for child in self.children:
      child.process(curr_frame)

  def __str__(self):
    return '\n'.join([str(child) for child in self.children])

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    out = set(
        itertools.chain(
            *[node.get_non_local_symbols() for node in self.children]))
    for symbol in self.get_defined_and_exported_symbols():
      out.discard(symbol)
    return out

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    chained = list(
        itertools.chain(*[
            node.get_defined_and_exported_symbols() for node in self.children
        ]))
    return set(chained)

  def pretty_print(self, indent=''):
    out = f'{super().pretty_print(indent)}\n'
    return out + "\n".join(
        child.pretty_print(indent + "  ") for child in self.children)


@attr.s
class ExpressionCfgNode(CfgNode):
  expression: Expression = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    self.expression.evaluate(curr_frame)

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    return self.expression.get_used_free_symbols()

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return []


@attr.s
class ImportCfgNode(CfgNode):
  module_path = attr.ib()
  parso_node = attr.ib()
  as_name = attr.ib(None)
  module_loader = attr.ib(kw_only=True)

  def _process_impl(self, curr_frame):
    name = self.as_name if self.as_name else self.module_path
    module = self.module_loader.get_module(self.module_path)

    if self.as_name:
      curr_frame[name] = module
    else:
      root_module = module.root()
      curr_frame[root_module.name] = root_module

    # info(f'Importing {module.path()} as {name}')  # Logs *constantly*
    collector.add_module_import(module.path(), self.as_name)

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    return []

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    if self.as_name:
      return [self.as_name]
    if '.' in self.module_path:
      return [self.module_path[:self.module_path.index('.')]]
    return [self.module_path]


@attr.s
class FromImportCfgNode(CfgNode):
  module_path = attr.ib()
  from_import_name = attr.ib()
  parso_node = attr.ib()
  as_name = attr.ib(None)
  module_loader = attr.ib(kw_only=True)

  def _process_impl(self, curr_frame):
    collector.add_from_import(self.module_path, self.from_import_name,
                              self.as_name)
    # Example: from foo import *
    if self.from_import_name == '*':
      module = self.module_loader.get_module(self.module_path)
      for name, pobject in module.items():
        curr_frame[name] = pobject
      return

    # Normal case.
    name = self.as_name if self.as_name else self.from_import_name

    pobject = self.module_loader.get_pobject_from_module(
        self.module_path, self.from_import_name)
    curr_frame[name] = pobject

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    return []

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    if self.as_name:
      return [self.as_name]
    return [self.from_import_name]


@attr.s
class NoOpCfgNode(CfgNode):
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    pass

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    return []

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return []


@attr.s
class AssignmentStmtCfgNode(CfgNode):
  # https://docs.python.org/3/reference/simple_stmts.html#assignment-statements
  left_variables: Expression = attr.ib(
      validator=attr.validators.instance_of(Expression))
  operator = attr.ib()  # Generally equals, but possibly +=, etc.
  right_expression: Expression = attr.ib()
  value_node = attr.ib()  # TODO: Delete.
  parso_node = attr.ib()

  def _process_impl(self, curr_frame, strict=False):
    # TODO: Handle operator.
    result = self.right_expression.evaluate(curr_frame)
    _assign_variables_to_results(curr_frame, self.left_variables, result)

  def __str__(self):
    return self._to_str()

  def _to_str(self):
    out = []
    if self.parso_node.get_code():
      out.append(f'{self.__class__.__name__}: {self.parso_node.get_code()}')
    return '\n'.join(out)

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    return self.right_expression.get_used_free_symbols()

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return self.left_variables.get_used_free_symbols()


@attr.s
class ForCfgNode(CfgNode):
  # Example for loop_variables in loop_expression: suite
  loop_variables: Expression = attr.ib()
  loop_expression: Expression = attr.ib()
  suite: 'GroupCfgNode' = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    _assign_variables_to_results(curr_frame, self.loop_variables,
                                 self.loop_expression.evaluate(curr_frame))
    self.suite.process(curr_frame)

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    loop_symbols = set(self.loop_variables.get_used_free_symbols())
    loop_expression_used_symbols = set(
        self.loop_expression.get_used_free_symbols())
    return loop_expression_used_symbols - loop_symbols

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return set(self.loop_variables.get_used_free_symbols()).union(
        set(self.suite.get_defined_and_exported_symbols()))

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}'


@attr.s
class WhileCfgNode(CfgNode):
  # Example while conditional_expression: suite else: else_suite
  conditional_expression: Expression = attr.ib()
  suite: 'CfgNode' = attr.ib()
  else_suite: 'CfgNode' = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    self.conditional_expression.evaluate(curr_frame)
    self.suite.process(curr_frame)
    self.else_suite.process(curr_frame)

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    out = self.suite.get_non_local_symbols().union(
        self.else_suite.get_non_local_symbols())
    return out.union(self.conditional_expression.get_used_free_symbols())

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return set(self.suite.get_defined_and_exported_symbols()).union(
        set(self.else_suite.get_defined_and_exported_symbols()))

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}\n{indent}Else\n{self.else_suite.pretty_print(indent=indent+"  ")}'


@attr.s
class WithCfgNode(CfgNode):
  # For 'else', (True, node).
  with_item_expression: Expression = attr.ib()
  as_expression: Union[Expression, None] = attr.ib(
  )  # TODO: NoOpExpression instead?
  suite: 'GroupCfgNode' = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    if self.as_expression:
      _assign_variables_to_results(
          curr_frame, self.as_expression,
          self.with_item_expression.evaluate(curr_frame))
    else:
      self.with_item_expression.evaluate(curr_frame)
    self.suite.process(curr_frame)

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    with_item_expression_symbols = self.with_item_expression.get_used_free_symbols(
    )
    as_expression_symbols = set(self.as_expression.get_used_free_symbols()
                               ) if self.as_expression else set()
    suite_symbols = set(self.suite.get_non_local_symbols())
    return set(
        itertools.chain(with_item_expression_symbols,
                        (suite_symbols - as_expression_symbols)))

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    if self.as_expression:
      return set(self.as_expression.get_used_free_symbols()).union(
          set(self.suite.get_defined_and_exported_symbols()))
    return set(self.suite.get_defined_and_exported_symbols())

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}'


@attr.s
class TryCfgNode(CfgNode):
  suite: CfgNode = attr.ib()
  except_nodes: List['ExceptCfgNode'] = attr.ib()
  else_suite: CfgNode = attr.ib()
  finally_suite: CfgNode = attr.ib()

  def _process_impl(self, curr_frame):
    self.suite.process(curr_frame)
    for except_cfg in self.except_nodes:
      except_cfg.process(curr_frame)
    self.else_suite.process(curr_frame)
    self.finally_suite.process(curr_frame)

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    return set(
        itertools.chain(*[
            node.get_non_local_symbols() for node in itertools.chain(
                [self.suite, self.finally_suite], self.except_nodes)
        ]))

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return set(
        itertools.chain(*[
            node.get_defined_and_exported_symbols() for node in itertools.chain(
                [self.suite, self.finally_suite], self.except_nodes)
        ]))

  def pretty_print(self, indent=''):
    out = f'{indent}Try\n{self.suite.pretty_print(indent+"  ")}'
    out += "\n".join(
        node.pretty_print(indent + "  ") for node in self.except_nodes)
    return out + f'\n{self.finally_suite.pretty_print(indent+"  ")}'


@attr.s
class ExceptCfgNode(CfgNode):
  exceptions: Expression = attr.ib()  # TODO: ???
  exception_variable: Union[VariableExpression, None] = attr.ib()
  suite: CfgNode = attr.ib()

  def _process_impl(self, curr_frame):
    '''Except clauses scope is bizarre.

    Essentially, they are not scoped blocks - but, the except variable is scoped to the block.
    so in:

    except Exception as e:
      b = 2

    `b` will be visible outside the block whereas `e` won't be.

    For this reason, we do a bit of weird finagling here in which we create a new frame, and merge
    it into the current frame after deleting `e` from it.'''

    new_frame = curr_frame.make_child(curr_frame.namespace, FrameType.EXCEPT)
    if self.exception_variable:
      new_frame[self.exception_variable] = UnknownObject(
          f'{self.exception_variable}')
    self.suite.process(new_frame)
    if self.exception_variable:
      del new_frame[self.exception_variable]
    for name, pobject in new_frame._locals.items():
      curr_frame[name] = pobject

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    out = set(self.suite.get_non_local_symbols())
    if self.exception_variable:
      out.discard(self.exception_variable.name)
    return out

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return self.suite.get_defined_and_exported_symbols()

  def pretty_print(self, indent=''):
    return f'{indent}except {self.exceptions} as {self.exception_variable}\n{self.suite.pretty_print(indent+"  ")}'


@attr.s
class IfCfgNode(CfgNode):
  # For 'else', (True, node).
  expression_node_tuples: List[Tuple[Expression, CfgNode]] = attr.ib()
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

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    out = set()
    for expression, node in self.expression_node_tuples:
      out = out.union(expression.get_used_free_symbols())
      out = out.union(node.get_non_local_symbols())
    return out

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    out = set()
    for _, node in self.expression_node_tuples:
      out = out.union(node.get_defined_and_exported_symbols())
    return out

  def pretty_print(self, indent=''):
    out = f'{indent}{type(self)}\n'
    return out + "\n".join(
        node.pretty_print(indent + "  ")
        for _, node in self.expression_node_tuples)


def _search_for_module(frame):
  if not frame:
    return None
  if isinstance(frame.namespace, Module):
    return frame.namespace
  return _search_for_module(frame._back)


@attr.s
class KlassCfgNode(CfgNode):
  name = attr.ib()
  suite = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    klass_name = f'{curr_frame.namespace.name}.{self.name}' if curr_frame.namespace else self.name
    klass = Klass(klass_name, curr_frame.namespace)
    curr_frame[self.name] = klass

    new_frame = curr_frame.make_child(
        frame_type=FrameType.KLASS, namespace=klass)
    # Locals defined in this frame are actually members of our class.
    self.suite.process(new_frame)
    klass._members = new_frame._locals
    for name, member in klass.items():

      def instance_member(f):
        if isinstance(f, Function):
          f.function_type = FunctionType.UNBOUND_INSTANCE_METHOD

      member.apply_to_values(instance_member)

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    return self.suite.get_non_local_symbols()

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return [self.name]

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}'


@attr.s
class FuncCfgNode(CfgNode):
  name = attr.ib()
  parameters = attr.ib()
  suite = attr.ib()
  _module = attr.ib(kw_only=True)
  _containing_func_node = attr.ib(kw_only=True)
  parso_node = attr.ib(kw_only=True)
  _child_functions = attr.ib(init=False, factory=list)

  def __attrs_post_init__(self):
    if self._containing_func_node:
      self._containing_func_node._child_functions.append(self)

  @instance_memoize
  def _get_local_and_ancestor_func_symbol_defs(self) -> Set[str]:
    out = self.suite.get_defined_and_exported_symbols()
    out = out.union([p.name for p in self.parameters])
    if self._containing_func_node:
      return out.union(
          self._containing_func_node._get_local_and_ancestor_func_symbol_defs())
    return out

  @instance_memoize
  def closure(self) -> Iterable[str]:
    if not self._containing_func_node:
      return []
    return set(self.suite.get_non_local_symbols()).intersection(
        self._containing_func_node._get_local_and_ancestor_func_symbol_defs())

  def _process_impl(self, curr_frame):
    processed_params = []
    for param in self.parameters:
      if param.default is None:
        processed_params.append(param)
      else:  # Process parameter defaults at the time of definition.
        default = param.default.evaluate(curr_frame)
        processed_params.append(
            Parameter(param.name, param.parameter_type, default))
    # Include full name.
    func_name = '.'.join([curr_frame.namespace.name, self.name
                         ]) if curr_frame.namespace else self.name
    func = FunctionImpl(
        name=func_name,
        namespace=curr_frame.namespace,
        parameters=processed_params,
        module=self._module,
        graph=self.suite,
        cell_symbols=self._get_new_cell_symbols())
    collector.add_function_node(func)

    # Handle closures, if any.
    if self.closure():
      bound_locals = {}
      for symbol in self.closure():
        assert symbol in curr_frame, 'Unbound local issue w/closure...'
        bound_locals[symbol] = curr_frame[symbol]
      func = BoundFunction(func, bound_locals=bound_locals)

    curr_frame[VariableExpression(self.name)] = func

  @instance_memoize
  def _get_new_cell_symbols(self):
    # New symbols are those that are in child closures but not in our own closure because they're
    # defined locally within this function.
    out = set(
        itertools.chain(*[func.closure() for func in self._child_functions]))
    for closure in self.closure():
      out.discard(closure)
    return out

  def __str__(self):
    return f'def {self.name}({self.parameters}):\n  {self.suite}\n'

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    out = set()
    for parameter in self.parameters:
      if parameter.default:
        out = out.union(parameter.default.get_used_free_symbols())
    out = out.union(self.suite.get_non_local_symbols())
    return out

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return [self.name]

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}'


@attr.s
class ReturnCfgNode(CfgNode):
  expression: Expression = attr.ib()
  parso_node = attr.ib()

  def _process_impl(self, curr_frame):
    curr_frame.add_return(self.expression.evaluate(curr_frame))

  @instance_memoize
  def get_non_local_symbols(self) -> Iterable[str]:
    return self.expression.get_used_free_symbols()

  @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return []
