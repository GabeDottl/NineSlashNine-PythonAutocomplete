from abc import ABC, abstractmethod
from wsgiref.validate import validator

import attr
from tensorflow.python.framework.errors_impl import UnimplementedError

from autocomplete.code_understanding.typing.pobjects import (
    AugmentedObject, FuzzyBoolean, FuzzyObject, PObject, UnknownObject)
from autocomplete.nsn_logging import debug, warning


class Expression(ABC):

  @abstractmethod
  def evaluate(self, curr_frame) -> PObject:
    raise NotImplementedError()  # abstract


@attr.s
class AnonymousExpression(Expression):
  pobject: PObject = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return self.pobject


@attr.s
class LiteralExpression(Expression):
  literal = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return AugmentedObject(self.literal)


@attr.s
class UnknownExpression(Expression):
  string = attr.ib()

  def evaluate(self, curr_frame):
    return UnknownObject(self.string)


# @attr.s
# class ForComprehensionExpression(Expression):
#   names = attr.ib()
#   source = attr.ib()

#   def evaluate(self, curr_frame) -> PObject:
#     pobject = self.expression.evaluate(curr_frame)
#     return AugmentedObject(pobject.bool_value().invert())


@attr.s
class NotExpression(Expression):
  expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    pobject = self.expression.evaluate(curr_frame)
    return AugmentedObject(pobject.bool_value().invert())


@attr.s
class TupleExpression(Expression):
  expressions = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return AugmentedObject(
        tuple(e.evaluate(curr_frame) for e in self.expressions))

  def __iter__(self):
    for expression in self.expressions:
      yield expression


@attr.s
class ListExpression(Expression):
  expressions = attr.ib(validator=[attr.validators.instance_of(list)])

  def evaluate(self, curr_frame) -> PObject:
    return AugmentedObject(
        list(e.evaluate(curr_frame) for e in self.expressions))

  def __iter__(self):
    for expression in self.expressions:
      yield expression


@attr.s
class CallExpression(Expression):
  function_expression = attr.ib(
      validator=[attr.validators.instance_of(Expression)])
  args = attr.ib(factory=list)
  kwargs = attr.ib(factory=dict)

  def evaluate(self, curr_frame) -> PObject:
    pobject = self.function_expression.evaluate(curr_frame)
    return pobject.call(self.args, self.kwargs, curr_frame)


@attr.s
class VariableExpression(Expression):
  name = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return curr_frame[self]


@attr.s
class StarExpression(Expression):
  '''E.g. *args - or more meaninglessly, *(a,b)'''
  base_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    raise NotImplementedError(f'*({self.base_expression})')


@attr.s
class AttributeExpression(Expression):
  base_expression: Expression = attr.ib()
  attribute: str = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    value: PObject = self.base_expression.evaluate(curr_frame)
    return value.get_attribute(self.attribute)


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


@attr.s
class IfElseExpression(Expression):
  true_result: Expression = attr.ib()
  conditional_expression: Expression = attr.ib()
  false_result: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    conditional = self.conditional_expression.evaluate(curr_frame)
    fuzzy_bool = conditional.bool_value()
    if fuzzy_bool == FuzzyBoolean.TRUE:
      return self.false_result.evaluate(curr_frame)
    if fuzzy_bool == FuzzyBoolean.MAYBE:
      return FuzzyObject([
          self.true_result.evaluate(curr_frame),
          self.false_result.evaluate(curr_frame)
      ])
    return self.true_result.evaluate(curr_frame)


@attr.s
class ForExpression(Expression):
  generator_expression: Expression = attr.ib()
  conditional_expression: Expression = attr.ib()
  iterable_expression: Expression = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    return self.generator_expression.evaluate(curr_frame)


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


@attr.s
class MathExpression(Expression):
  left = attr.ib()
  operator = attr.ib()
  right = attr.ib()
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
    l = self.left.evaluate(curr_frame)
    r = self.right.evaluate(curr_frame)
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


@attr.s
class ComparisonExpression(Expression):
  left = attr.ib()
  operator = attr.ib()
  right = attr.ib()

  def evaluate(self, curr_frame) -> PObject:
    # comp_op: '<'|'>'|'=='|'>='|'<='|'<>'|'!='|'in'|'not' 'in'|'is'|'is' 'not'
    l = self.left.evaluate(curr_frame)
    r = self.right.evaluate(curr_frame)
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


Variable = Expression
