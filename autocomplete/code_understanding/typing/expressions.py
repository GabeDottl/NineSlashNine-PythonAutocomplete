import itertools
from abc import ABC, abstractmethod
from typing import Dict, Iterable, List
from wsgiref.validate import validator

import attr

from autocomplete.code_understanding.typing.pobjects import (AugmentedObject,
                                                             FuzzyBoolean,
                                                             FuzzyObject,
                                                             PObject,
                                                             UnknownObject)
from autocomplete.nsn_logging import debug, warning


class Expression(ABC):

  @abstractmethod
  def evaluate(self, curr_frame) -> PObject:
    raise NotImplementedError()  # abstract

  @abstractmethod
  def get_used_free_symbols(self) -> Iterable[str]:
    ''' Gets symbols used in a free context - i.e. not as attributes.'''


@attr.s
class AnonymousExpression(Expression):
  pobject: PObject = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return self.pobject

  def get_used_free_symbols(self) -> Iterable[str]:
    return []


@attr.s
class LiteralExpression(Expression):
  literal = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return AugmentedObject(self.literal)

  def get_used_free_symbols(self) -> Iterable[str]:
    return []


@attr.s
class UnknownExpression(Expression):
  string = attr.ib()

  def evaluate(self, curr_frame):
    return UnknownObject(self.string)

  def get_used_free_symbols(self) -> Iterable[str]:
    return []


@attr.s
class NotExpression(Expression):
  expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    pobject = self.expression.evaluate(curr_frame)
    return AugmentedObject(pobject.bool_value().invert())

  def get_used_free_symbols(self) -> Iterable[str]:
    return self.expression.get_used_free_symbols()


@attr.s
class ListExpression(Expression):
  # May be an ItemListExpression or a ForComprehensionExpression.
  source_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return self.source_expression.evalaute(curr_frame)

  def __iter__(self):
    return iter(self.source_expression)

  def get_used_free_symbols(self) -> Iterable[str]:
    return self.source_expression.get_used_free_symbols()


@attr.s
class TupleExpression(ListExpression):
  ...


@attr.s
class ItemListExpression(Expression):
  '''Used for cased like: 1,2,3 - as in a tuple (1,2,3) or a list [1,2,3] or an arg list.'''
  expressions = attr.ib(validator=[attr.validators.instance_of(list)])

  def evaluate(self, curr_frame) -> PObject:
    return AugmentedObject(
        list(e.evaluate(curr_frame) for e in self.expressions))

  def __iter__(self):
    for expression in self.expressions:
      yield expression

  def get_used_free_symbols(self) -> Iterable[str]:
    # TODO: set
    return list(
        itertools.chain(
            *[expr.get_used_free_symbols() for expr in self.expressions]))


@attr.s
class ForComprehensionExpression(Expression):
  ''' As in: ` for x in func2(y)` - not to be confused with a for-block.'''
  # generator_expression for target_variables in iterable_expression
  generator_expression: Expression = attr.ib()
  target_variables: Expression = attr.ib()
  iterable_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return self.generator_expression.evaluate(curr_frame)

  def get_used_free_symbols(self) -> Iterable[str]:
    generator_free_symbols = self.generator_expression.get_used_free_symbols()
    target_symbols = self.target_variables.get_used_free_symbols()
    iterable_symbols = self.iterable_symbols.get_used_free_symbols()
    generator_non_locals = set(generator_free_symbols) - set(target_symbols)
    return set(itertools.chain(generator_non_locals, iterable_symbols))


@attr.s
class CallExpression(Expression):
  function_expression = attr.ib(
      validator=[attr.validators.instance_of(Expression)])
  args: List[Expression] = attr.ib(factory=list)
  kwargs: Dict[str, Expression] = attr.ib(factory=dict)

  def evaluate(self, curr_frame) -> PObject:
    pobject = self.function_expression.evaluate(curr_frame)
    return pobject.call(self.args, self.kwargs, curr_frame)

  def get_used_free_symbols(self) -> Iterable[str]:
    out = set(self.function_expression.get_used_free_symbols())
    out = out.union(
        itertools.chain(*[expr.get_used_free_symbols() for expr in self.args]))
    out = out.union(
        itertools.chain(
            *[expr.get_used_free_symbols() for expr in self.kwargs.values()]))
    return out


@attr.s
class VariableExpression(Expression):
  name = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return curr_frame[self]

  def get_used_free_symbols(self) -> Iterable[str]:
    return [self.name]


@attr.s
class StarExpression(Expression):
  '''E.g. *args - or more meaninglessly, *(a,b)'''
  base_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    raise NotImplementedError(f'*({self.base_expression})')

  def get_used_free_symbols(self) -> Iterable[str]:
    return self.base_expression.get_used_free_symbols()


@attr.s
class AttributeExpression(Expression):
  base_expression: Expression = attr.ib()
  attribute: str = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    value: PObject = self.base_expression.evaluate(curr_frame)
    return value.get_attribute(self.attribute)

  def get_used_free_symbols(self) -> Iterable[str]:
    return self.base_expression.get_used_free_symbols()


@attr.s
class SubscriptExpression(Expression):
  base_expression: Expression = attr.ib()
  subscript_list = attr.ib()

  @subscript_list.validator
  def _validate_subscript_list(self, attribute, values):
    for value in values:
      if not isinstance(value, Expression):
        raise ValueError(value)

  def evaluate(self, curr_frame) -> PObject:
    return self.get(curr_frame)

  def get(self, curr_frame):
    pobject = self.base_expression.evaluate(curr_frame)
    values = []
    for e in self.subscript_list:
      values.append(e.evaluate(curr_frame))
    return pobject.get_item(tuple(values))

  def set(self, curr_frame, value):
    pobject = self.base_expression.evaluate(curr_frame)
    values = []
    for e in self.subscript_list:
      values.append(e.evaluate(curr_frame))
    return pobject.set_item(tuple(values), value)

  def get_used_free_symbols(self) -> Iterable[str]:
    return self.base_expression.get_used_free_symbols()


@attr.s
class IfElseExpression(Expression):
  true_expression: Expression = attr.ib()
  conditional_expression: Expression = attr.ib()
  false_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    conditional = self.conditional_expression.evaluate(curr_frame)
    fuzzy_bool = conditional.bool_value()
    if fuzzy_bool == FuzzyBoolean.TRUE:
      return self.false_expression.evaluate(curr_frame)
    if fuzzy_bool == FuzzyBoolean.MAYBE:
      return FuzzyObject([
          self.true_expression.evaluate(curr_frame),
          self.false_expression.evaluate(curr_frame)
      ])
    return self.true_expression.evaluate(curr_frame)

  def get_used_free_symbols(self) -> Iterable[str]:
    return set(
        itertools.chain(expr.get_used_free_symbols()
                        for expr in (self.true_expression,
                                     self.conditional_expression,
                                     self.false_expression)))


@attr.s
class FactorExpression(Expression):
  operator = attr.ib()
  expression: Expression = attr.ib()
  parso_node = attr.ib()

  def evaluate(self, curr_frame):
    if self.operator == '+':
      return self.expression.evaluate(curr_frame)
    if self.operator == '-':
      return MathExpression(
          LiteralExpression(-1), '*', self.expression,
          self.parso_node).evaluate(curr_frame)
    if self.operator == '~':
      debug(f'Skipping inversion and just returning expression')
      return self.expression.evaluate(curr_frame)

  def get_used_free_symbols(self) -> Iterable[str]:
    return self.expression.get_used_free_symbols()


@attr.s
class MathExpression(Expression):
  left_expression: Expression = attr.ib()
  operator = attr.ib()
  right_expression: Expression = attr.ib()
  parso_node = attr.ib()

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
    warning(f'MathExpression failed: {l}{self.operator}{r}')
    return UnknownObject(f'{self.parso_node.get_code()}')

  def get_used_free_symbols(self) -> Iterable[str]:
    return set(self.left_expression.get_used_free_symbols() +
               self.right_expression.get_used_free_symbols())


@attr.s
class ComparisonExpression(Expression):
  left_expression: Expression = attr.ib()
  operator = attr.ib()
  right_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    # comp_op: '<'|'>'|'=='|'>='|'<='|'<>'|'!='|'in'|'not' 'in'|'is'|'is' 'not'
    l = self.left_expression.evaluate(curr_frame)
    r = self.right_expression.evaluate(curr_frame)
    # TODO
    return UnknownObject(f'{l}{self.operator}{r}')

    if self.operator == '<':
      return l < r
    if self.operator == '>':
      return l > r
    if self.operator == '==':
      return l == r
    if self.operator == '>=':
      return l >= r
    if self.operator == '<=':
      return l <= r
    # if self.operator == '<>': return l <> r
    if self.operator == '!=':
      return l != r
    if self.operator == 'in':
      return l in r
    if self.operator == 'not in':
      return l not in r
    if self.operator == 'is':
      return l is r
    if self.operator == 'is not':
      return l is not r

    assert False, f'Cannot handle {self.operator} yet.'

  def get_used_free_symbols(self) -> Iterable[str]:
    return set(self.left_expression.get_used_free_symbols() +
               self.right_expression.get_used_free_symbols())


Variable = Expression
