from abc import ABC, abstractmethod

import attr

from autocomplete.code_understanding.typing.pobjects import (
    FuzzyObject, UnknownObject, AugmentedObject, literal_to_fuzzy)
from autocomplete.nsn_logging import info


class Expression(ABC):

  @abstractmethod
  def evaluate(self, curr_frame) -> FuzzyObject:
    raise NotImplementedError()  # abstract


@attr.s
class LiteralExpression(Expression):
  literal = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    return literal_to_fuzzy(self.literal)


class UnknownExpression(Expression):

  def evaluate(self, curr_frame):
    return UnknownObject('')


# @attr.s
# class ForComprehensionExpression(Expression):
#   names = attr.ib()
#   source = attr.ib()

#   def evaluate(self, curr_frame) -> FuzzyObject:
#     pobject = self.expression.evaluate(curr_frame)
#     return AugmentedObject(pobject.bool_value().invert())


@attr.s
class NotExpression(Expression):
  expression = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    pobject = self.expression.evaluate(curr_frame)
    return AugmentedObject(pobject.bool_value().invert())


@attr.s
class TupleExpression(Expression):
  expressions = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    return FuzzyObject(
        [tuple(e.evaluate(curr_frame) for e in self.expressions)])


@attr.s
class ListExpression(Expression):
  expressions = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    return FuzzyObject([list(e.evaluate(curr_frame) for e in self.expressions)])


@attr.s
class CallExpression(Expression):
  function_variable = attr.ib()
  args = attr.ib(factory=list)
  kwargs = attr.ib(factory=dict)

  def evaluate(self, curr_frame) -> FuzzyObject:
    pobject = curr_frame[self.function_variable]
    function_assignment = pobject.value()
    return function_assignment.call(self.args, self.kwargs, curr_frame)


@attr.s
class AttributeExpression(Expression):
  base_expression = attr.ib()
  attribute = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    value: FuzzyObject = self.base_expression.evaluate(curr_frame)
    return value.get_attribute(self.attribute)


@attr.s
class SubscriptExpression(Expression):
  base_expression = attr.ib()
  subscript_list = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    value = self.base_expression.evaluate(curr_frame)
    return value[tuple(e.evaluate(curr_frame) for e in self.subscript_list)]


@attr.s
class VariableExpression(Expression):
  name = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    return curr_frame[self]


@attr.s
class IfExpression(Expression):
  positive_expression = attr.ib()
  conditional_expression = attr.ib()
  negative_expression = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    conditional = self.conditional_expression.evaluate(curr_frame)
    if not conditional:
      return self.negative_expression.evaluate(curr_frame)
    if conditional.is_ambiguous():
      out = FuzzyObject()
      out._values = [
          self.positive_expression.evaluate(curr_frame),
          self.negative_expression.evaluate(curr_frame)
      ]
      return out
    return self.positive_expression.evaluate(curr_frame)


@attr.s
class ForExpression(Expression):
  generator_expression = attr.ib()
  conditional_expression = attr.ib()
  iterable_expression = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    return self.generator_expression.evaluate(curr_frame)

@attr.s
class FactorExpression(Expression):
  operator = attr.ib()
  expression = attr.ib()

  def evaluate(self, curr_frame):
    if self.operator == '+': return self.expression.evaluate(curr_frame)
    if self.operator == '-': return MathExpression(LiteralExpression(-1), '*', self.expression).evaluate(curr_frame)
    if self.operator == '~': 
      info(f'Skipping inversion and just returning expression')
      return self.expression.evaluate(curr_frame)
    

@attr.s
class MathExpression(Expression):
  left = attr.ib()
  operator = attr.ib()
  right = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
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
    assert False, f'Cannot handle {self.operator} yet.'


@attr.s
class ComparisonExpression(Expression):
  left = attr.ib()
  operator = attr.ib()
  right = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    # comp_op: '<'|'>'|'=='|'>='|'<='|'<>'|'!='|'in'|'not' 'in'|'is'|'is' 'not'
    l = self.left.evaluate(curr_frame)
    r = self.right.evaluate(curr_frame)
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


@attr.s
class AssignmentExpressionStatement:  # Looks like an Expression, but not technically one.
  left_variables = attr.ib()
  operator = attr.ib()  # Generally equals, but possibly +=, etc.
  right_expression = attr.ib()

  def evaluate(self, curr_frame) -> FuzzyObject:
    # TODO: Handle operator.
    result = self.right_expression.evaluate(curr_frame)
    # info(f'result: {result}')
    # info(f'self.right_expression: {self.right_expression}')
    if len(self.left_variables) == 1:
      info(self.left_variables[0])
      curr_frame[self.left_variables[0]] = result
      info(f'result: {result}')
      # info(
      #     f'curr_frame[self.left_variables[0]]: {curr_frame[self.left_variables[0]]}'
      # )
    else:
      for i, variable in enumerate(self.left_variables):
        # TODO: Handle this properly...
        curr_frame[variable] = result[i]


Variable = Expression
