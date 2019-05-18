import itertools
from abc import ABC, abstractmethod
from builtins import NotImplementedError
from functools import wraps, partial
from typing import Dict, Iterable, List, Set, Tuple, Union

import attr
from . import collector, symbol_context, expressions
from .errors import (AmbiguousFuzzyValueError, ParsingError, assert_unexpected_parso)
from .expressions import (Expression, StarredExpression, SubscriptExpression, VariableExpression,
                          _assign_variables_to_results)
from .frame import Frame, FrameType
from .language_objects import (BoundFunction, Function, FunctionImpl, FunctionType, Klass, Module, ModuleImpl,
                               NativeModule, Parameter, SimplePackageModule)
from .pobjects import (AugmentedObject, FuzzyBoolean, FuzzyObject, LazyObject, UnknownObject)
from .utils import (assert_returns_type, instance_memoize)
from ...nsn_logging import error, info, warning

# from .collector import Collector


@attr.s
class ParseNode:
  lineno: int = attr.ib()
  col_offset: int = attr.ib()
  native_node: int = attr.ib(None)
  # Extra information derived from parsing which may be useful for debugging or refactoring.
  # Usually this won't be set.
  extras = attr.ib(None)

  def get_code(self):
    if hasattr(self.native_node, 'get_code'):
      return self.native_node.get_code()
    import astor
    return astor.to_source(self.native_node)


class CfgNode(ABC):
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))

  def process(self, curr_frame):
    with collector.ParseNodeContext(self.parse_node):
      self._process_impl(curr_frame)

  @abstractmethod
  def _process_impl(self, curr_frame):
    ...

  @abstractmethod
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    '''Gets all symbols that are going to be nonlocal/locally defined outside this node.

    This does not include globals.
    '''

  @abstractmethod
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    '''Symbols that's that are both defined within this node and are visible outside of it.

    For classes and functions, these are just the names of the class/function. For other blocks,
    this will generally include all of their assignments.
    '''

  def get_descendents_of_types(self, type_):
    return []

  def strip_descendents_of_types(self, type_, recursive=False) -> 'CfgNode':
    return self

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}'


@attr.s(slots=True)
class GroupCfgNode(CfgNode):
  children: List[CfgNode] = attr.ib(factory=list)
  parse_node = attr.ib(None)

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

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    out = symbol_context.merge_symbol_context_dicts(*[node.get_non_local_symbols() for node in self.children])
    for symbol in self.get_defined_and_exported_symbols():
      if symbol in out:
        del out[symbol]
    return out

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    chained = set(itertools.chain(*[node.get_defined_and_exported_symbols() for node in self.children]))
    return chained

  def get_descendents_of_types(self, type_):
    return itertools.chain(filter(lambda x: isinstance(x, type_), self.children),
                           *[c.get_descendents_of_types(type_) for c in self.children])

  def strip_descendents_of_types(self, type_, recursive=False) -> CfgNode:
    if recursive:
      return GroupCfgNode(
          list(
              x.strip_descendents_of_types(type_, recursive)
              for x in filter(lambda n: not isinstance(n, type_), self.children)))
    return GroupCfgNode(list(filter(lambda n: not isinstance(n, type_), self.children)))

  def pretty_print(self, indent=''):
    out = f'{super().pretty_print(indent)}\n'
    return out + "\n".join(child.pretty_print(indent + "  ") for child in self.children)


@attr.s(slots=True)
class ExpressionCfgNode(CfgNode):
  expression: Expression = attr.ib(validator=attr.validators.instance_of(Expression))
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))

  def _process_impl(self, curr_frame):
    self.expression.evaluate(curr_frame)

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return self.expression.get_used_free_symbols()

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return []


@attr.s(slots=True)
class ImportCfgNode(CfgNode):
  module_path = attr.ib()  # TODO: Rename to name
  source_dir: str = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))
  as_name = attr.ib(None)
  module_loader = attr.ib(kw_only=True)

  @instance_memoize
  def get_module_key(self):
    return self.module_loader.get_module_info_from_name(self.module_path, self.source_dir)[0]

  def _process_impl(self, curr_frame):
    name = self.as_name if self.as_name else self.module_path
    module = self.module_loader.get_module(self.module_path, self.source_dir)

    if self.as_name:
      curr_frame[name] = AugmentedObject(module, imported=True)
    elif '.' in self.module_path:
      # When python imports a module, it does not include information about containing packages
      # in it, so we dynamically add a structure to our module. Because we cache imported modules,
      # we don't attach this to |module| so we don't risk sharing this imported hierachy across
      # frames.
      ancestor_module_hierarchy = self.module_path.split('.')
      last_module = None
      current_name = None
      for name in ancestor_module_hierarchy[:-1]:
        current_name = f'{current_name}.{name}' if current_name else name
        obj = None
        if last_module and last_module.has_attribute(name):
          obj = last_module.get_attribute(name)
        elif not last_module and name in curr_frame:
          obj = curr_frame[name]

        ancestor_module = None
        if obj is not None:
          try:
            ancestor_module = obj.value()
          except AmbiguousFuzzyValueError:
            pass

        # Module importing is kind of funny. Essentially, when importing a path like `import a.b.c`
        # each value on that path must be a module (incl. packages only with inits).
        # The modules contained with each of the modules on this path may be defined purely by
        # imports and are dynamically added to as more things are imported. If a package already
        # exists, we'll add the modules simple as a member.
        if ancestor_module is None or not isinstance(ancestor_module, Module):
          module_key, is_package, module_type = self.module_loader.get_module_info_from_name(
              current_name, self.source_dir)
          # assert is_package
          ancestor_module = SimplePackageModule(current_name,
                                                module_type,
                                                filename=module_key.path,
                                                is_package=True,
                                                members={},
                                                module_loader=self.module_loader)

        if last_module:
          last_module.add_members({name: AugmentedObject(ancestor_module, imported=True)})
        else:
          root_module = ancestor_module
        last_module = ancestor_module

      last_module[ancestor_module_hierarchy[-1]] = AugmentedObject(module, imported=True)
      curr_frame[root_module.name] = AugmentedObject(root_module, imported=True)
    else:  # Free module - e.g. import a.
      # If this package has been partially imported, bring in the members that have been imported
      # already.
      if name in curr_frame and isinstance(name, SimplePackageModule):
        assert module.is_package
        for name, member in curr_frame[name].get_members().items():
          module.set_attribute(name, member)

      curr_frame[module.name] = AugmentedObject(module, imported=True)
    collector.add_module_import(module.name, self.as_name)

  # def imported_symbol_name(self):
  #   base = self.as_name if self.as_name else self.module_path
  #   if '.' in base:
  #     return base[:base.find('.')]
  #   return base

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return {}

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    if self.as_name:
      return [self.as_name]
    if '.' in self.module_path:
      return [self.module_path[:self.module_path.index('.')]]
    return [self.module_path]


@attr.s(slots=True)
class FromImportCfgNode(CfgNode):
  module_path = attr.ib()
  from_import_name_alias_dict: Dict[str, str] = attr.ib()
  source_dir: str = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))
  as_name = attr.ib(None)
  module_loader = attr.ib(kw_only=True)

  @instance_memoize
  def get_module_key(self):
    return self.module_loader.get_module_info_from_name(self.module_path, self.source_dir)[0]

  def _process_impl(self, curr_frame):
    for from_import_name, as_name in self.from_import_name_alias_dict.items():
      collector.add_from_import(self.module_path, from_import_name, as_name)
      # Example: from foo import *
      if from_import_name == '*':
        # TODO: Create index of symbols in each package so this doesn't require loading object?
        # This sort of import should be rather uncommon, so perhaps not super-worthwhile...

        # Python's kind of funny. If |module| is a package, this will only bring in the modules in
        # that package which have already been explcitly imported. So, given a.b and a.c modules,
        # if we have from a import *, b and c will only be brought in to the namespace if they were
        # already imported. Such subtleties..
        module = self.module_loader.get_module(self.module_path, collector.get_current_context_dir())
        if '__all__' in module:
          try:
            all_iter = iter(module['__all__'].value())
          except TypeError:
            pass
          else:
            for val in all_iter:
              val_str = val.value()
              if val_str in module:
                curr_frame[val_str] = module[val_str]
        else:
          # Python does not include private members when importing with star.
          for name, pobject in filter(lambda kv: kv[0][0] != '_', module.items()):
            curr_frame[name] = AugmentedObject(pobject, imported=True)
        break

      # Normal case.
      name = as_name if as_name else from_import_name

      curr_dir = collector.get_current_context_dir()
      # We must use a partial in here to process our loop variables immediately rather than accessing them
      # from a cell object to make multiple imports work. Otherwise all imports will load the last item in the
      # list.
      lo_name = f'{self.module_path}.{from_import_name}'
      pobject = LazyObject(lo_name,
                           partial(self.module_loader.get_pobject_from_module, self.module_path,
                                   from_import_name, curr_dir),
                           imported=True)
      curr_frame[name] = pobject

  def imported_symbol_names(self):
    out = []
    for from_import_name, as_name in self.from_import_name_alias_dict.items():
      out.append(as_name if as_name else from_import_name)
    return out

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return {}

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return self.imported_symbol_names()


@attr.s(slots=True)
class NoOpCfgNode(CfgNode):
  parse_node = attr.ib(None)

  def _process_impl(self, curr_frame):
    pass

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return {}

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return []


@attr.s(slots=True)
class AssignmentStmtCfgNode(CfgNode):
  # https://docs.python.org/3/reference/simple_stmts.html#assignment-statements
  left_variables: Expression = attr.ib(validator=attr.validators.instance_of(Expression))
  operator = attr.ib()  # Generally equals, but possibly +=, etc.
  right_expression: Expression = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))
  type_hint_expression = attr.ib(None)

  def _process_impl(self, curr_frame, strict=False):
    # TODO: Handle operator.
    result = self.right_expression.evaluate(curr_frame)
    _assign_variables_to_results(curr_frame, self.left_variables, result)

  def __str__(self):
    return self._to_str()

  def _to_str(self):
    out = []
    if self.parse_node.get_code():
      out.append(f'{self.__class__.__name__}: {self.parse_node.get_code()}')
    return '\n'.join(out)

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    if self.type_hint_expression:
      return symbol_context.merge_symbol_context_dicts(self.right_expression.get_used_free_symbols(),
                                                       self.type_hint_expression.get_used_free_symbols())
    return self.right_expression.get_used_free_symbols()

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return self.left_variables.get_used_free_symbols()


@attr.s(slots=True)
class ForCfgNode(CfgNode):
  # Example for loop_variables in loop_expression: suite
  loop_variables: Expression = attr.ib()
  loop_expression: Expression = attr.ib()
  suite: 'GroupCfgNode' = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))
  else_suite: 'GroupCfgNode' = attr.ib(factory=NoOpCfgNode)  # TODO: Remove default

  def _process_impl(self, curr_frame):
    _assign_variables_to_results(curr_frame, self.loop_variables, self.loop_expression.evaluate(curr_frame))
    self.suite.process(curr_frame)

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    loop_symbols = self.loop_variables.get_used_free_symbols()
    loop_expression_used_symbols = self.loop_expression.get_used_free_symbols()
    for name in loop_symbols.keys():
      if name in loop_expression_used_symbols:
        del loop_expression_used_symbols[name]
    return loop_expression_used_symbols

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return set(self.loop_variables.get_used_free_symbols()).union(
        set(self.suite.get_defined_and_exported_symbols())).union(
            self.else_suite.get_defined_and_exported_symbols())

  def get_descendents_of_types(self, type_):
    return itertools.chain(self.suite.get_descendents_of_types(type_),
                           self.else_suite.get_descendents_of_types(type_))

  def strip_descendents_of_types(self, type_, recursive=False) -> CfgNode:
    suite = self.suite.strip_descendents_of_types(type_, recursive=recursive)
    else_suite = self.else_suite.strip_descendents_of_types(type_, recursive=recursive)
    return ForCfgNode(self.loop_variables, self.loop_expression, suite, self.parse_node, else_suite)

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}'


@attr.s(slots=True)
class WhileCfgNode(CfgNode):
  # Example while conditional_expression: suite else: else_suite
  conditional_expression: Expression = attr.ib()
  suite: 'CfgNode' = attr.ib()
  else_suite: 'CfgNode' = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))

  def _process_impl(self, curr_frame):
    self.conditional_expression.evaluate(curr_frame)
    self.suite.process(curr_frame)
    self.else_suite.process(curr_frame)

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    out = symbol_context.merge_symbol_context_dicts(self.suite.get_non_local_symbols(),
                                                    self.else_suite.get_non_local_symbols())
    return symbol_context.merge_symbol_context_dicts(out, self.conditional_expression.get_used_free_symbols())

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return set(self.suite.get_defined_and_exported_symbols()).union(
        set(self.else_suite.get_defined_and_exported_symbols()))

  def get_descendents_of_types(self, type_):
    return itertools.chain(self.suite.get_descendents_of_types(type_),
                           self.else_suite.get_descendents_of_types(type_))

  def strip_descendents_of_types(self, type_, recursive=False) -> CfgNode:
    suite = self.suite.strip_descendents_of_types(type_, recursive=recursive)
    else_suite = self.else_suite.strip_descendents_of_types(type_, recursive=recursive)
    return WhileCfgNode(self.conditional_expression, suite, else_suite, self.parse_node)

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}\n{indent}Else\n{self.else_suite.pretty_print(indent=indent+"  ")}'


@attr.s(slots=True)
class WithCfgNode(CfgNode):
  # For 'else', (True, node).
  with_item_expression: Expression = attr.ib()
  as_expression: Union[Expression, None] = attr.ib()  # TODO: NoOpExpression instead?
  suite: 'GroupCfgNode' = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))

  def _process_impl(self, curr_frame):
    if self.as_expression:
      _assign_variables_to_results(curr_frame, self.as_expression,
                                   self.with_item_expression.evaluate(curr_frame))
    else:
      self.with_item_expression.evaluate(curr_frame)
    self.suite.process(curr_frame)

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    with_item_expression_symbols = self.with_item_expression.get_used_free_symbols()
    as_expression_symbols = self.as_expression.get_used_free_symbols() if self.as_expression else {}
    suite_symbols = self.suite.get_non_local_symbols()
    for name in as_expression_symbols.keys():
      if name in suite_symbols:
        del suite_symbols[name]
    return symbol_context.merge_symbol_context_dicts(with_item_expression_symbols, suite_symbols)

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    if self.as_expression:
      return set(self.as_expression.get_used_free_symbols()).union(
          set(self.suite.get_defined_and_exported_symbols()))
    return set(self.suite.get_defined_and_exported_symbols())

  def get_descendents_of_types(self, type_):
    return self.suite.get_descendents_of_types(type_)

  def strip_descendents_of_types(self, type_, recursive=False) -> CfgNode:
    suite = self.suite.strip_descendents_of_types(type_, recursive=recursive)
    return WithCfgNode(self.with_item_expression, self.as_expression, suite, self.parse_node)

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}'


@attr.s(slots=True)
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

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(*[
        node.get_non_local_symbols()
        for node in itertools.chain([self.suite, self.else_suite, self.finally_suite], self.except_nodes)
    ])

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return set(
        itertools.chain(*[
            node.get_defined_and_exported_symbols()
            for node in itertools.chain([self.suite, self.else_suite, self.finally_suite], self.except_nodes)
        ]))

  def get_descendents_of_types(self, type_):
    return itertools.chain(self.suite.get_descendents_of_types(type_),
                           self.else_suite.get_descendents_of_types(type_),
                           self.finally_suite.get_descendents_of_types(type_))

  def strip_descendents_of_types(self, type_, recursive=False) -> CfgNode:
    suite = self.suite.strip_descendents_of_types(type_, recursive=recursive)
    else_suite = self.else_suite.strip_descendents_of_types(type_, recursive=recursive)
    finally_suite = self.finally_suite.strip_descendents_of_types(type_, recursive=recursive)
    except_nodes = [x.strip_descendents_of_types(type_, recursive=recursive) for x in self.except_nodes]
    return TryCfgNode(suite=suite,
                      except_nodes=except_nodes,
                      else_suite=else_suite,
                      finally_suite=finally_suite)

  def pretty_print(self, indent=''):
    out = f'{indent}Try\n{self.suite.pretty_print(indent+"  ")}'
    out += "\n".join(node.pretty_print(indent + "  ") for node in self.except_nodes)
    return out + f'\n{self.finally_suite.pretty_print(indent+"  ")}'


@attr.s(slots=True)
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

    new_frame = curr_frame.make_child(curr_frame.namespace, FrameType.NORMAL)  # TODO: EXCEPT
    if self.exception_variable:
      new_frame[self.exception_variable] = UnknownObject(f'{self.exception_variable}')
    self.suite.process(new_frame)
    if self.exception_variable:
      del new_frame[self.exception_variable]
    for name, pobject in new_frame._locals.items():
      curr_frame[name] = pobject

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    out = self.suite.get_non_local_symbols()
    if self.exceptions:
      out = symbol_context.merge_symbol_context_dicts(self.exceptions.get_used_free_symbols())
    if self.exception_variable:
      if self.exception_variable.name in out:
        del out[self.exception_variable.name]
    return out

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return self.suite.get_defined_and_exported_symbols()

  def get_descendents_of_types(self, type_):
    return self.suite.get_descendents_of_types(type_)

  def strip_descendents_of_types(self, type_, recursive=False) -> CfgNode:
    suite = self.suite.strip_descendents_of_types(type_, recursive=recursive)
    return ExceptCfgNode(self.exceptions, self.exception_variable, suite)

  def pretty_print(self, indent=''):
    return f'{indent}except {self.exceptions} as {self.exception_variable}\n{self.suite.pretty_print(indent+"  ")}'


@attr.s(slots=True)
class IfCfgNode(CfgNode):
  # For 'else', (True, node).
  expression_node_tuples: List[Tuple[Expression, CfgNode]] = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))

  def _process_impl(self, curr_frame):
    for expression, node in self.expression_node_tuples:
      # result = expression.evaluate(curr_frame)
      # if result.bool_value() == FuzzyBoolean.TRUE:
      #   # Expression is definitely true - evaluate and stop here.
      #   node.process(curr_frame)
      #   break
      # elif result.bool_value() == FuzzyBoolean.FALSE:
      #   # Expression is definitely false - skip.
      #   # TODO: Process for collector.
      #   continue
      # else:  # Completely ambiguous / MAYBE.
      node.process(curr_frame)

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    out = {}
    for expression, node in self.expression_node_tuples:
      out = symbol_context.merge_symbol_context_dicts(out, expression.get_used_free_symbols(),
                                                      node.get_non_local_symbols())
    return out

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    out = set()
    for _, node in self.expression_node_tuples:
      out = out.union(node.get_defined_and_exported_symbols())
    return out

  def get_descendents_of_types(self, type_):
    return itertools.chain(*[c.get_descendents_of_types(type_) for e, c in self.expression_node_tuples])

  def pretty_print(self, indent=''):
    out = f'{indent}{type(self)}\n'
    return out + "\n".join(node.pretty_print(indent + "  ") for _, node in self.expression_node_tuples)


def _search_for_module(frame):
  if not frame:
    return None
  if isinstance(frame.namespace, Module):
    return frame.namespace
  return _search_for_module(frame._back)


@attr.s(slots=True)
class KlassCfgNode(CfgNode):
  name = attr.ib()
  base_class_expressions = attr.ib()
  suite: GroupCfgNode = attr.ib()
  _module = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))

  def _process_impl(self, curr_frame):
    klass_name = f'{curr_frame.namespace.name}.{self.name}' if curr_frame.namespace else self.name
    #
    klass = Klass(klass_name, self._module.name)
    curr_frame[self.name] = klass

    new_frame = curr_frame.make_child(frame_type=FrameType.KLASS, namespace=klass)
    # Locals defined in this frame are actually members of our class.
    self.suite.process(new_frame)
    klass._members = new_frame._locals
    for name, member in klass.items():

      def instance_member(f):
        if isinstance(f, Function):
          f.function_type = FunctionType.UNBOUND_INSTANCE_METHOD

      member.apply_to_values(instance_member)

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    out = {}
    # Classes are weird - if I defined a symbol as a class member, it can be used by other non-func
    # class members, but must be referenced as an attribute of the class or an instance within
    # functions.
    for child in filter(lambda x: not isinstance(x, FuncCfgNode), self.suite):
      out = symbol_context.merge_symbol_context_dicts(out, child.get_non_local_symbols())
    # Drop locally defined symbols *before* we add in the missing symbols from and child functions.
    for symbol in self.suite.get_defined_and_exported_symbols():
      if symbol in out:
        del out[symbol]
    for child in filter(lambda x: isinstance(x, FuncCfgNode), self.suite):
      out = symbol_context.merge_symbol_context_dicts(out, child.get_non_local_symbols())
    for base_class_expression in self.base_class_expressions:
      out = symbol_context.merge_symbol_context_dicts(out, base_class_expression.get_used_free_symbols())
    return out

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return [self.name]

  def get_descendents_of_types(self, type_):
    return self.suite.get_descendents_of_types(type_)

  def strip_descendents_of_types(self, type_, recursive=False) -> CfgNode:
    suite = self.suite.strip_descendents_of_types(type_, recursive=recursive)
    return KlassCfgNode(self.name, self.base_class_expressions, suite, self._module, self.parse_node)

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}'


@attr.s(slots=True)
class FuncCfgNode(CfgNode):
  name = attr.ib()
  parameters = attr.ib()
  suite = attr.ib()
  return_type_hint_expression = attr.ib(None)
  _module = attr.ib(kw_only=True)
  _containing_func_node = attr.ib(kw_only=True)
  parse_node = attr.ib(kw_only=True)
  _child_functions = attr.ib(kw_only=True, factory=list)

  def __attrs_post_init__(self):
    if self._containing_func_node:
      self._containing_func_node._child_functions.append(self)

  # @instance_memoize
  def _get_local_and_ancestor_func_symbol_defs(self) -> Set[str]:
    out = self.suite.get_defined_and_exported_symbols()
    out = out.union([p.name for p in self.parameters])
    if self._containing_func_node:
      return out.union(self._containing_func_node._get_local_and_ancestor_func_symbol_defs())
    return out

  # @instance_memoize
  def closure(self) -> Iterable[str]:
    if not self._containing_func_node:
      return []
    return set(self.suite.get_non_local_symbols()).intersection(
        self._containing_func_node._get_local_and_ancestor_func_symbol_defs())

  def _process_impl(self, curr_frame):
    processed_params = []
    for param in self.parameters:
      if param.default_expression is None:
        processed_params.append(param)
      else:  # Process parameter defaults at the time of definition.
        default = param.default_expression.evaluate(curr_frame)
        processed_params.append(Parameter(param.name, param.parameter_type, default_value=default))
    # Include full name.
    func_name = '.'.join([curr_frame.namespace.name, self.name]) if curr_frame.namespace else self.name
    func = FunctionImpl(name=func_name,
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

  # @instance_memoize
  def _get_new_cell_symbols(self):
    # New symbols are those that are in child closures but not in our own closure because they're
    # defined locally within this function.
    out = set(itertools.chain(*[func.closure() for func in self._child_functions]))
    for closure in self.closure():
      out.discard(closure)
    return out

  def __str__(self):
    return f'def {self.name}({self.parameters}):\n  {self.suite}\n'

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    out = self.suite.get_non_local_symbols()
    # Note that we iterate through parameters twice because a symbol may be nonlocally used
    # in a parameter default but defined by another parameter. We don't want to exclude the symbol
    # in this case, thus we add-it back in in the 2nd loop.
    for parameter in self.parameters:
      if parameter.name in out:
        del out[parameter.name]

    for parameter in self.parameters:
      if parameter.default_expression:
        out = symbol_context.merge_symbol_context_dicts(out,
                                                        parameter.default_expression.get_used_free_symbols())
      if parameter.type_hint_expression:
        out = symbol_context.merge_symbol_context_dicts(
            out, parameter.type_hint_expression.get_used_free_symbols())
    if self.return_type_hint_expression:
      out = symbol_context.merge_symbol_context_dicts(
          out, self.return_type_hint_expression.get_used_free_symbols())

    return out

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return [self.name]

  def get_descendents_of_types(self, type_):
    return self.suite.get_descendents_of_types(type_)

  def strip_descendents_of_types(self, type_, recursive=False) -> CfgNode:
    suite = self.suite.strip_descendents_of_types(type_, recursive=recursive)
    return FuncCfgNode(name=self.name,
                       parameters=self.parameters,
                       suite=suite,
                       module=self._module,
                       containing_func_node=self._containing_func_node,
                       parse_node=self.parse_node,
                       child_functions=self._child_functions)

  def pretty_print(self, indent=''):
    return f'{indent}{type(self)}\n{self.suite.pretty_print(indent=indent+"  ")}'


@attr.s(slots=True)
class ReturnCfgNode(CfgNode):
  expression: Expression = attr.ib()
  parse_node = attr.ib(validator=attr.validators.instance_of(ParseNode))

  def _process_impl(self, curr_frame):
    curr_frame.add_return(self.expression.evaluate(curr_frame))

  # @instance_memoize # Result dict may be modified.
  @assert_returns_type(dict)
  def get_non_local_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return self.expression.get_used_free_symbols()

  # @instance_memoize
  def get_defined_and_exported_symbols(self) -> Iterable[str]:
    return []
