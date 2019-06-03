import itertools
from abc import ABC, abstractmethod
from typing import (Dict, Iterable, List, Union)
import _ast

import attr

from . import symbol_context
from ...nsn_logging import (debug, info)
from .pobjects import (FuzzyObject, NativeObject, PObject, PObjectType, NONE_POBJECT, UnknownObject,
                       pobject_from_object)
from .utils import assert_returns_type


class Expression(ABC):
  def to_ast(self) -> _ast.Expression:
    return _ast.Expr(self._to_ast())

  def _to_ast(self):
    raise NotImplementedError()

  @abstractmethod
  def evaluate(self, curr_frame) -> PObject:
    raise NotImplementedError()  # abstract

  @abstractmethod
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    ''' Gets symbols used in a free context - i.e. not as attributes.'''


@attr.s(slots=True)
class LiteralExpression(Expression):
  literal = attr.ib()

  def _to_ast(self):
    if isinstance(self.literal, bool) or self.literal == None:
      return _ast.NameConstant(self.literal)
    if isinstance(self.literal, (int, float, complex)):
      return _ast.Num(self.literal)
    if isinstance(self.literal, str):
      return _ast.Str(self.literal)
    if isinstance(self.literal, bytes):
      return _ast.Bytes(self.literal)
    if self.literal == Ellipsis:
      return _ast.Ellipsis()
    # TODO: Figure out wtf _ast
    raise NotImplementedError()

  def evaluate(self, curr_frame) -> PObject:
    return NativeObject(self.literal)

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return {}


@attr.s(slots=True)
class YieldExpression(Expression):
  expression: Union[Expression, None] = attr.ib()
  is_from_expression = attr.ib()  # yield from <expr> or yield <expr> or just yield.

  def _to_ast(self):
    if self.expression:
      assert False  # is_From todo
      return _ast.Yield(self.expression._to_ast())
    return _ast.Yield()

  def evaluate(self, curr_frame) -> PObject:
    if self.expression:
      return self.expression.evaluate(curr_frame)
    return NONE_POBJECT

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    if self.expression:
      return self.expression.get_used_free_symbols()
    return {}


@attr.s(slots=True)
class NotExpression(Expression):
  expression: Expression = attr.ib()

  def _to_ast(self):
    return _ast.Not(self.expression._to_ast())

  def evaluate(self, curr_frame) -> PObject:
    pobject = self.expression.evaluate(curr_frame)
    return pobject.invert()

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return self.expression.get_used_free_symbols()


@attr.s(slots=True)
class InvertExpression(NotExpression):
  def _to_ast(self):
    return _ast.Invert(self.expression._to_ast())


@attr.s(slots=True)
class AndOrExpression(Expression):
  operator: _ast.boolop = attr.ib()
  expressions: List[Expression] = attr.ib()

  def _to_ast(self):
    # op = _ast.And() if self.operator == 'and' else _ast.Or()
    return _ast.BoolOp(self.operator, [e._to_ast() for e in self.expressions])

  def evaluate(self, curr_frame) -> PObject:
    # TODO
    return UnknownObject('Blegh.')
    # l = self.expressions[0].evaluate(curr_frame)
    # r = self.expressions[1].evaluate(curr_frame)
    # if self.operator == 'or':
    #   return l.or_expr(r)
    # assert self.operator == 'and'
    # return l.and_expr(r)

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(*[e.get_used_free_symbols() for e in self.expressions])


@attr.s(slots=True)
class ComparisonExpression(Expression):
  left_expression: Expression = attr.ib()
  ops = attr.ib()
  comparators: List[Expression] = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    # comp_op: '<'|'>'|'=='|'>='|'<='|'<>'|'!='|'in'|'not' 'in'|'is'|'is' 'not'
    # l = self.left_expression.evaluate(curr_frame)
    # r = self.right_expression.evaluate(curr_frame)
    # TODO
    return UnknownObject(f'{self.left_expression}{self.ops}{self.comparators}')

    # if self.operator == '<':
    #   return l < r
    # if self.operator == '>':
    #   return l > r
    # if self.operator == '==':
    #   return l == r
    # if self.operator == '>=':
    #   return l >= r
    # if self.operator == '<=':
    #   return l <= r
    # # if self.operator == '<>': return l <> r
    # if self.operator == '!=':
    #   return l != r
    # if self.operator == 'in':
    #   return l in r
    # if self.operator == 'not in':
    #   return l not in r
    # if self.operator == 'is':
    #   return l is r
    # if self.operator == 'is not':
    #   return l is not r

    # assert False, f'Cannot handle {self.operator} yet.'

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(self.left_expression.get_used_free_symbols(),
                                                     *[e.get_used_free_symbols() for e in self.comparators])


@attr.s(slots=True)
class ListExpression(Expression):
  # May be an ItemListExpression or a ForComprehensionExpression.
  source_expression: Expression = attr.ib(validator=attr.validators.instance_of(Expression))

  # expr_context: ExprContext = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return self.source_expression.evaluate(curr_frame)

  def __iter__(self):
    return iter(self.source_expression)

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return self.source_expression.get_used_free_symbols()


@attr.s(slots=True)
class TupleExpression(ListExpression):
  ...


@attr.s(slots=True)
class ItemListExpression(Expression):
  '''Used for cased like: 1,2,3 - as in a tuple (1,2,3) or a list [1,2,3] or an arg list.'''
  expressions: List[Expression] = attr.ib(validator=[attr.validators.instance_of(list)])

  def evaluate(self, curr_frame) -> PObject:
    assert curr_frame
    return NativeObject(list(e.evaluate(curr_frame) for e in self.expressions))

  def __len__(self):
    return len(self.expressions)

  def __getitem__(self, index):
    return self.expressions[index]

  def __iter__(self):
    for expression in self.expressions:
      yield expression

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(
        *[expr.get_used_free_symbols() for expr in self.expressions])


def _assign_variables_to_results(curr_frame, variable, result):
  if (hasattr(variable, '__len__') and len(variable) == 1):
    variable = variable[0]
  if not hasattr(variable, '__iter__'):
    # collector.add_variable_assignment(variable,
    #                                   f'({parse_node.get_code().strip()})')
    assert isinstance(variable, Expression), variable
    if isinstance(variable, SubscriptExpression):
      variable.set(curr_frame, result)
    else:
      # TODO: Handle this properly...
      curr_frame[variable] = result
  else:
    # Recursively process variables.
    for i, variable_item in enumerate(variable):
      if isinstance(variable_item, StarredExpression):
        debug(f'Mishandling star assignment')
        # TODO: a, *b = 1,2,3,4 # b = 2,3,4.
        _assign_variables_to_results(curr_frame, variable_item.base_expression,
                                     result.get_item(curr_frame, pobject_from_object(i)))
      else:
        _assign_variables_to_results(curr_frame, variable_item,
                                     result.get_item(curr_frame, pobject_from_object(i)))


@attr.s(slots=True)
class CallExpression(Expression):
  function_expression = attr.ib(validator=[attr.validators.instance_of(Expression)])
  args: List[Expression] = attr.ib(factory=list)
  kwargs: Dict[str, Expression] = attr.ib(factory=dict)
  parse_node = attr.ib(kw_only=True)

  def evaluate(self, curr_frame) -> PObject:
    pobject = self.function_expression.evaluate(curr_frame)
    evaluated_args = [arg.evaluate(curr_frame) for arg in self.args]
    evaluated_kwargs = {name: arg.evaluate(curr_frame) for name, arg in self.kwargs.items()}
    out = pobject.call(curr_frame, evaluated_args, evaluated_kwargs)
    return out

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    if isinstance(self.function_expression, VariableExpression):
      out = {
          self.function_expression.name: symbol_context.CallSymbolContext(self.args, self.kwargs,
                                                                          self.parse_node)
      }
    else:
      out = self.function_expression.get_used_free_symbols()

    out = symbol_context.merge_symbol_context_dicts(out,
                                                    *[expr.get_used_free_symbols() for expr in self.args])
    out = symbol_context.merge_symbol_context_dicts(
        out, *[expr.get_used_free_symbols() for expr in self.kwargs.values()])
    return out


@attr.s(slots=True)
class VariableExpression(Expression):
  name = attr.ib(validator=attr.validators.instance_of(str))
  parse_node = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return curr_frame[self]

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return {self.name: symbol_context.RawSymbolContext(self.parse_node)}


@attr.s(slots=True)
class ForComprehension:
  target_variables: Expression = attr.ib()
  iterable_expression: Expression = attr.ib()
  ifs: List[ComparisonExpression] = attr.ib()
  is_async: bool = attr.ib()

  def process_into_new_frame(self, curr_frame) -> 'Frame':
    # TODO: Fill out proper.
    new_frame = curr_frame.make_child(curr_frame.namespace)
    _assign_variables_to_results(new_frame, self.target_variables,
                                 self.iterable_expression.evaluate(new_frame))
    return new_frame

  # @instance_memoize
  def get_defined_symbols(self):
    return self.target_variables.get_used_free_symbols()

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    non_locals = self.iterable_expression.get_used_free_symbols()
    for if_ in self.ifs:
      non_locals = symbol_context.merge_symbol_context_dicts(non_locals, if_.get_used_free_symbols())
    for symbol in self.get_defined_symbols():
      if symbol in non_locals:
        del non_locals[symbol]
    return non_locals


@attr.s(slots=True)
class ForComprehensionExpression(Expression):
  ''' As in: ` for x in func2(y)` - not to be confused with a for-block.'''
  # generator_expression for target_variables in iterable_expression.
  generator_expression: Expression = attr.ib()
  for_comprehensions: List[ForComprehension] = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    new_frame = self.for_comprehension.process_into_new_frame(curr_frame)
    out = self.generator_expression.evaluate(new_frame)
    return out

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    generator_free_symbols = self.generator_expression.get_used_free_symbols()
    for for_comprehension in self.for_comprehensions:
      for symbol in for_comprehension.get_defined_symbols():
        if symbol in generator_free_symbols:
          del generator_free_symbols[symbol]
    return symbol_context.merge_symbol_context_dicts(
        generator_free_symbols,
        *[for_comprehension.get_used_free_symbols() for for_comprehension in self.for_comprehensions])

@attr.s(slots=True)
class StarredExpression(Expression):
  '''E.g. *args - or more meaninglessly, *(a,b)'''
  operator: str = attr.ib()  # * or **
  base_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    out = pobject_from_object(self.base_expression.evaluate(curr_frame).iterator())
    out.pobject_type = PObjectType.STARRED if self.operator == '*' else PObjectType.DOUBLE_STARRED
    return out

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return self.base_expression.get_used_free_symbols()


@attr.s(slots=True)
class KeyValueAssignment:
  key: Expression = attr.ib()
  value: Expression = attr.ib()

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return self.value.get_used_free_symbols()


@attr.s(slots=True)
class KeyValueForComp:
  key: Expression = attr.ib()
  value: Expression = attr.ib()
  for_comps: List[ForComprehension] = attr.ib(validator=attr.validators.instance_of(list))

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    out = self.value.get_used_free_symbols()
    for for_comp in self.for_comps:
      for symbol in for_comp.get_defined_symbols():
        if symbol in out:
          del out[symbol]
    return symbol_context.merge_symbol_context_dicts(
        out, *[for_comp.get_used_free_symbols() for for_comp in self.for_comps])
    # return out


@attr.s(slots=True)
class SetExpression(Expression):
  values: List[Union[StarredExpression, Expression, ForComprehensionExpression]] = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return NativeObject(set())  # TODO

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(
        *[value.get_used_free_symbols() for value in self.values])


@attr.s(slots=True)
class DictExpression(Expression):
  values: List[Union[StarredExpression, KeyValueAssignment, KeyValueForComp]] = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    out = NativeObject({})  #LazyObject('{}', lambda: NativeObject({}))
    for value in self.values:
      if isinstance(value, KeyValueAssignment):
        k = value.key.evaluate(curr_frame)
        v = value.value.evaluate(curr_frame)
        # try:
        out.set_item(curr_frame, k, v)
        # except (AmbiguousFuzzyValueError) as e:
        #   # Unhashable.
        #   warning(e)
      elif isinstance(value, StarredExpression):
        assert value.operator == '**'
        base_pobject = value.base_expression.evaluate(curr_frame)
        # TODO: Make work with LazyObject.
        # if isinstance(base_pobject, NativeObject):
        try:
          out.update_dict(base_pobject)
        except TypeError as e:
          info(e)
          pass
      else:
        assert isinstance(value, KeyValueForComp)
        pass  # TODO
    return out

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(
        *[value.get_used_free_symbols() for value in self.values])


@attr.s(slots=True)
class AttributeExpression(Expression):
  base_expression: Expression = attr.ib()
  attribute: str = attr.ib()
  parse_node = attr.ib(kw_only=True)

  def evaluate(self, curr_frame) -> PObject:
    value: PObject = self.base_expression.evaluate(curr_frame)
    return value.get_attribute(self.attribute)

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    if isinstance(self.base_expression, VariableExpression):
      return {
          self.base_expression.name: symbol_context.AttributeSymbolContext(self.attribute, self.parse_node)
      }
    return self.base_expression.get_used_free_symbols()


@attr.s(slots=True)
class Slice:
  lower: Expression = attr.ib(None)
  upper: Expression = attr.ib(None)
  step: Expression = attr.ib(None)

  def _to_ast(self):
    return _ast.Slice(self.lower._to_ast() if self.lower else None,
                      self.upper._to_ast() if self.upper else None,
                      self.step._to_ast() if self.step else None)

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    out = self.lower.get_used_free_symbols() if self.lower else {}
    out = symbol_context.merge_symbol_context_dicts(out,
                                                    self.upper.get_used_free_symbols()) if self.upper else out
    return symbol_context.merge_symbol_context_dicts(out,
                                                     self.step.get_used_free_symbols()) if self.step else out


@attr.s(slots=True)
class ExtSlice:
  slices: List = attr.ib(validator=attr.validators.instance_of(Iterable))

  def _to_ast(self):
    return _ast.ExtSlice([s._to_ast() for s in self.slices])

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(*[s.get_used_free_symbols() for s in self.slices])


@attr.s(slots=True)
class IndexSlice:
  expression: Expression = attr.ib()

  def _to_ast(self):
    return _ast.Index(self.expression._to_ast())

  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return self.expression.get_used_free_symbols()


@attr.s(slots=True)
class SubscriptExpression(Expression):
  base_expression: Expression = attr.ib()
  _slice: Union[Slice, ExtSlice, IndexSlice] = attr.ib()
  # subscript_list_expression: Expression = attr.ib()
  parse_node = attr.ib(kw_only=True)

  def _to_ast(self):
    return _ast.Subscript(self.base_expression._to_ast(), self._slice._to_ast())

  def evaluate(self, curr_frame) -> PObject:
    return self.get(curr_frame)

  def get(self, curr_frame):
    pobject = self.base_expression.evaluate(curr_frame)
    # TODO: Delete this method or change NativeObject.
    return pobject.get_item(curr_frame, NativeObject(0))

  def set(self, curr_frame, value):
    pobject = self.base_expression.evaluate(curr_frame)
    # TODO: Delete this method or change NativeObject.
    return pobject.set_item(curr_frame, NativeObject(0), value)

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    if isinstance(self.base_expression, VariableExpression):
      out = {self.base_expression.name: symbol_context.SubscriptSymbolContext(self._slice, self.parse_node)}
    else:
      out = self.base_expression.get_used_free_symbols()
    return symbol_context.merge_symbol_context_dicts(out, self._slice.get_used_free_symbols())


@attr.s(slots=True)
class IfElseExpression(Expression):
  true_expression: Expression = attr.ib()
  conditional_expression: Expression = attr.ib()
  false_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    conditional = self.conditional_expression.evaluate(curr_frame)
    # fuzzy_bool = conditional.bool_value()
    # if fuzzy_bool == FuzzyBoolean.TRUE:
    #   return self.false_expression.evaluate(curr_frame)
    # if fuzzy_bool == FuzzyBoolean.MAYBE:
    return FuzzyObject(
        [self.true_expression.evaluate(curr_frame),
         self.false_expression.evaluate(curr_frame)])
    # return self.true_expression.evaluate(curr_frame)

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(*[
        expr.get_used_free_symbols()
        for expr in (self.true_expression, self.conditional_expression, self.false_expression)
    ])


@attr.s(slots=True)
class FactorExpression(Expression):
  operator = attr.ib()
  expression: Expression = attr.ib()
  parse_node = attr.ib()

  def evaluate(self, curr_frame):
    if self.operator == '+':
      return self.expression.evaluate(curr_frame)
    if self.operator == '-':
      return MathExpression(LiteralExpression(-1), '*', self.expression, self.parse_node).evaluate(curr_frame)
    if self.operator == '~':
      debug(f'Skipping inversion and just returning expression')
      return self.expression.evaluate(curr_frame)

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return self.expression.get_used_free_symbols()


@attr.s(slots=True)
class MathExpression(Expression):
  left_expression: Expression = attr.ib()
  operator = attr.ib()
  right_expression: Expression = attr.ib()
  parse_node = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    # expr: xor_expr ('|' xor_expr)*
    # xor_expr: and_expr ('^' and_expr)*
    # and_expr: shift_expr ('&' shift_expr)*
    # shift_expr: arith_expr (('<<'|'>>') arith_expr)*
    # arith_expr: term (('+'|'-') term)*
    # term: factor (('*'|'@'|'/'|'%'|'//') factor)*
    # factor: ('+'|'-'|'~') factor | power
    # power: atom_expr ['**' factor]
    # TODO: handle options...
    l = self.left_expression.evaluate(curr_frame)
    r = self.right_expression.evaluate(curr_frame)
    try:
      if self.operator == '|':
        return l | r
      if self.operator == '^':
        return l ^ r
      if self.operator == '&':
        return l & r
      if self.operator == '<<':
        return l << r
      if self.operator == '>>':
        return l >> r
      if self.operator == '+':
        return l + r
      if self.operator == '-':
        return l - r
      if self.operator == '*':
        return l * r
      if self.operator == '@':
        return l @ r
      if self.operator == '/':
        return l / r
      if self.operator == '%':
        return l % r
      if self.operator == '//':
        return l // r
      # if self.operator == '~': return l ~ r  # Invalid syntax?
      if self.operator == '**':
        return l**r

      if self.operator == '*':
        return l * r
    except TypeError:
      ...
    debug(f'MathExpression failed: {l}{self.operator}{r}')
    return UnknownObject(f'{self.parse_node.get_code()}')

  # @instance_memoize
  @assert_returns_type(dict)
  def get_used_free_symbols(self) -> Dict[str, symbol_context.SymbolContext]:
    return symbol_context.merge_symbol_context_dicts(self.left_expression.get_used_free_symbols(),
                                                     self.right_expression.get_used_free_symbols())


# Variable = Expression
