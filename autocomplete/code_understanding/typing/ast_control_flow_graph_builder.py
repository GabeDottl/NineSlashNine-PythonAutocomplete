import ast

import astor
import attr

import _ast
from autocomplete.code_understanding.typing import errors
from autocomplete.code_understanding.typing.control_flow_graph_nodes import *  # Temporary.
from autocomplete.code_understanding.typing.expressions import *  # Temporary.
from autocomplete.nsn_logging import warning


@attr.s
class AstControlFlowGraphBuilder:
  module_loader = attr.ib()
  _module: 'Module' = attr.ib()
  root: GroupCfgNode = attr.ib(factory=GroupCfgNode)

  def graph_from_source(self, source):
    try:
      ast_node = ast.parse(source)
    except SyntaxError as e:
      raise errors.AstUnableToParse(e)
    visitor = Visitor(module=self._module, container_stack=[])
    visitor.visit(ast_node)
    return visitor.root

@attr.s
class ListPopper:
  l = attr.ib()
  value = attr.ib()

  def __enter__(self):
    self.l.append(self.value)

  def __exit__(self, exc_type, exc_value, traceback):
    self.l.pop()


# For a rather help
# https://docs.python.org/3/library/ast.html#abstract-grammar
@attr.s
class Visitor(ast.NodeVisitor):
  _module = attr.ib()
  _container_stack = attr.ib(factory=list)
  root = attr.ib(None, init=False)

  def generic_visit(self, ast_node):
    if isinstance(ast_node, EXPRESSIONS_TUPLE):
      return ExpressionCfgNode(expression_from_node(ast_node))
    super().generic_visit(ast_node)

  def visit_Module(self, ast_node):
    assert not self.root
    self.root = GroupCfgNode()
    # with self.container_context(self.root):
    with ListPopper(self._container_stack, self.root):
      self.generic_visit(ast_node)
    # self._container_stack.pop()
    assert not self._container_stack

  def visit_Interactive(self, ast_node):
    # stmt* body)
    self.generic_visit(ast_node)

  def visit_Expression(self, ast_node):
    # expr body)
    self.generic_visit(ast_node)

  def visit_Assign(self, ast_node):
    self._container_stack[-1].children.append(
        AssignmentStmtCfgNode(variables_from_targets(ast_node.targets),
                              '=',
                              expression_from_node(ast_node.value),
                              parse_node=parse_from_ast(ast_node)))

  def visit_FunctionDef(self, ast_node):
    # (identifier name, arguments args, stmt* body, expr* decorator_list, expr? returns)
    self.generic_visit(ast_node)

  def visit_AsyncFunctionDef(self, ast_node):
    # (identifier name, arguments args, stmt* body, expr* decorator_list, expr? returns)
    self.generic_visit(ast_node)

  def visit_ClassDef(self, ast_node):
    # (identifier name, expr* bases, keyword* keywords, stmt* body, expr* decorator_list)
    self.generic_visit(ast_node)

  def visit_Return(self, ast_node):
    # (expr? value)
    self.generic_visit(ast_node)

  def visit_Delete(self, ast_node):
    # (expr* targets)
    self.generic_visit(ast_node)

  def visit_AugAssign(self, ast_node):
    # (expr target, operator op, expr value)
    self.generic_visit(ast_node)

  def visit_AnnAssign(self, ast_node):
    # (expr target, expr annotation, expr? value, int simple)          -- 'simple' indicates that we annotate simple name without parens
    self.generic_visit(ast_node)

  def visit_For(self, ast_node):
    # (expr target, expr iter, stmt* body, stmt* orelse) # use 'orelse' because else is a keyword in target languages
    self.generic_visit(ast_node)

  def visit_AsyncFor(self, ast_node):
    # (expr target, expr iter, stmt* body, stmt* orelse)
    self.generic_visit(ast_node)

  def visit_While(self, ast_node):
    # (expr test, stmt* body, stmt* orelse)
    self.generic_visit(ast_node)

  def visit_If(self, ast_node):
    # (expr test, stmt* body, stmt* orelse)
    self.generic_visit(ast_node)

  def visit_With(self, ast_node):
    # (withitem* items, stmt* body)
    self.generic_visit(ast_node)

  def visit_AsyncWith(self, ast_node):
    # (withitem* items, stmt* body)
    self.generic_visit(ast_node)

  def visit_Raise(self, ast_node):
    # (expr? exc, expr? cause)
    self.generic_visit(ast_node)

  def visit_Try(self, ast_node):
    # (stmt* body, excepthandler* handlers, stmt* orelse, stmt* finalbody)
    self.generic_visit(ast_node)

  def visit_Assert(self, ast_node):
    # (expr test, expr? msg)
    self.generic_visit(ast_node)

  def visit_Import(self, ast_node):
    # (alias* names)
    self.generic_visit(ast_node)

  def visit_ImportFrom(self, ast_node):
    # (identifier? module, alias* names, int? level)
    self.generic_visit(ast_node)

  def visit_Global(self, ast_node):
    # (identifier* names)
    self.generic_visit(ast_node)

  def visit_Nonlocal(self, ast_node):
    # (identifier* names)
    self.generic_visit(ast_node)

  def visit_Expr(self, ast_node):
    # (expr value)
    self.generic_visit(ast_node)

  # def visit_Pass(self, ast_node):
  #   self.generic_visit(ast_node)

  # def visit_Break(self, ast_node):
  #   self.generic_visit(ast_node)

  # def visit_Continue(self, ast_node):
  #   self.generic_visit(ast_node)


def variables_from_targets(ast_nodes):
  return ItemListExpression([expression_from_node(ast_node) for ast_node in ast_nodes])


EXPRESSIONS_TUPLE = (_ast.BoolOp, _ast.BinOp, _ast.UnaryOp, _ast.Lambda, _ast.IfExp, _ast.Dict, _ast.Set,
                     _ast.ListComp, _ast.SetComp, _ast.DictComp, _ast.GeneratorExp, _ast.Await, _ast.Yield,
                     _ast.YieldFrom, _ast.Compare, _ast.Call, _ast.Num, _ast.Str, _ast.FormattedValue,
                     _ast.JoinedStr, _ast.Bytes, _ast.NameConstant, _ast.Ellipsis, _ast.Constant,
                     _ast.Attribute, _ast.Subscript, _ast.Starred, _ast.Name, _ast.List, _ast.Tuple)


def expression_from_node(ast_node):
  assert isinstance(ast_node, EXPRESSIONS_TUPLE)
  if isinstance(ast_node, _ast.BoolOp):
    # (boolop op, expr* values)
    expression_from_boolop(ast_node)
  if isinstance(ast_node, _ast.BinOp):
    # (expr left, operator op, expr right)
    return expression_from_binop(ast_node)
  if isinstance(ast_node, _ast.UnaryOp):
    # (unaryop op, expr operand)
    return expression_from_unaryop(ast_node)
  if isinstance(ast_node, _ast.Lambda):
    # (arguments args, expr body)
    return UnknownExpression(astor.to_source(ast_node))
  if isinstance(ast_node, _ast.IfExp):
    # (expr test, expr body, expr orelse)
    return IfElseExpression(expression_from_node(ast_node.body), expression_from_node(ast_node.test),
                            expression_from_node(ast_node.orelse))
  if isinstance(ast_node, _ast.Dict):
    # (expr* keys, expr* values)
    return DictExpression([
        KeyValueAssignment(expression_from_node(k), expression_from_node(v))
        for k, v in zip(ast_node.keys, ast_node.values)
    ])
  if isinstance(ast_node, _ast.Set):
    # (expr* elts)
    return SetExpression([expression_from_node(node) for node in ast_node.elts])
  if isinstance(ast_node, _ast.ListComp):
    # (expr elt, comprehension* generators)
    return ForComprehensionExpression(expression_from_node(ast_node.elt),
                                      for_comprehension_from_comprehensions(ast_node.comprehensions))
  if isinstance(ast_node, _ast.SetComp):
    # (expr elt, comprehension* generators)
    return SetExpression([
        ForComprehensionExpression(expression_from_node(ast_node.elt),
                                   for_comprehension_from_comprehensions(ast_node.comprehensions))
    ])
  if isinstance(ast_node, _ast.DictComp):
    # (expr key, expr value, comprehension* generators)
    return DictExpression([
        KeyValueForComp(expression_from_node(ast_node.key), expression_from_node(ast_node.value),
                        for_comprehension_from_comprehensions(ast_node.comprehensions))
    ])
  if isinstance(ast_node, _ast.GeneratorExp):
    # (expr elt, comprehension* generators)
    return ForComprehensionExpression(expression_from_node(ast_node.elt),
                                      for_comprehension_from_comprehensions(ast_node.comprehensions))
  if isinstance(ast_node, _ast.Await):
    # (expr value)
    # TODO
    return expression_from_node(ast_node)
  if isinstance(ast_node, _ast.Yield):
    # (expr? value)
    if hasattr(ast_node, 'value'):
      return expression_from_node(ast_node.value)
    import astor
    return UnknownExpression(astor.to_source(ast_node))
  if isinstance(ast_node, _ast.YieldFrom):
    # (expr value)
    # TODO: Generator
    return expression_from_node(ast_node.value)
  if isinstance(ast_node, _ast.Compare):
    # (expr left, cmpop* ops, expr* comparators)
    # cmpop = Eq | NotEq | Lt | LtE | Gt | GtE | Is | IsNot | In | NotIn
    return comparison_expression_from_compare(ast_node)
  if isinstance(ast_node, _ast.Call):
    # (expr func, expr* args, keyword* keywords)
    args = [expression_from_node(arg) for arg in ast_node.args]
    kwargs_val, kwargs = kwargs_from_keywords(ast_node.keywords)
    # kwargs_val = **dict
    # TODO: Clean this up with parso impl.
    if kwargs_val:
      args.append(kwargs_val)
    return CallExpression(expression_from_node(ast_node.func), args, kwargs)
  if isinstance(ast_node, _ast.Num):
    # (object n) -- a number as a PyObject.
    return LiteralExpression(ast_node.n)
  if isinstance(ast_node, _ast.Str):
    # (string s) -- need to specify raw, unicode, etc?
    return LiteralExpression(ast_node.s)
  if isinstance(ast_node, _ast.FormattedValue):
    # (expr value, int? conversion, expr? format_spec)
    # TODO
    return expression_from_node(ast_node.value)
  if isinstance(ast_node, _ast.JoinedStr):
    # (expr* values) # TODO: ???
    return ItemListExpression([expression_from_node(node) in ast_node.values])
  if isinstance(ast_node, _ast.Bytes):
    # (bytes s)  # TODO: parso.
    return LiteralExpression(ast_node.s)
  if isinstance(ast_node, _ast.NameConstant):
    # singleton: None, True or False
    # (singleton value)
    return LiteralExpression(ast_node.value)
  if isinstance(ast_node, _ast.Ellipsis):
    return LiteralExpression(...)
  if isinstance(ast_node, _ast.Constant):
    # (constant value)
    return LiteralExpression(ast_node.value)
  if isinstance(ast_node, _ast.Attribute):
    # (expr value, identifier attr, expr_context ctx)
    return AttributeExpression(expression_from_node(ast_node.value), ast_node.attr)
  if isinstance(ast_node, _ast.Subscript):
    # (expr value, slice slice, expr_context ctx)
    return SubscriptExpression(expression_from_node(ast_node.value), expression_from_slice(ast_node.slice))
  if isinstance(ast_node, _ast.Starred):
    # (expr value, expr_context ctx)
    return StarredExpression('*', expression_from_node(ast_node))
  if isinstance(ast_node, _ast.Name):
    # (identifier id, expr_context ctx)
    return VariableExpression(ast_node.id)
  if isinstance(ast_node, _ast.List):
    # (expr* elts, expr_context ctx)
    return ListExpression(variables_from_targets(ast_node.elts))
  if isinstance(ast_node, _ast.Tuple):
    # (expr* elts, expr_context ctx)
    return TupleExpression(variables_from_targets(ast_node.elts))
  warning(f'Unhandled Expression type {type(ast_node)}')
  import astor
  return UnknownExpression(astor.to_source(ast_node))


def string_from_boolop(boolop):
  return 'and' if isinstance(boolop, _ast.And) else 'or'


def expression_from_boolop(ast_node):
  op = string_from_boolop(ast_node.op)
  last_expression = AndOrExpression(expression_from_node(ast_node.values[0]), op,
                                    expression_from_node(ast_node.values[1]))
  for node in ast_node.values[2:]:
    last_expression = AndOrExpression(last_expression, op, expression_from_node(node))
  return last_expression


def operator_symbol_from_operator(operator):
  if isinstance(operator, _ast.Add):
    return '+'
  if isinstance(operator, _ast.Sub):
    return '-'
  if isinstance(operator, _ast.Mult):
    return '*'
  if isinstance(operator, _ast.MatMult):
    return '@'
  if isinstance(operator, _ast.Div):
    return '/'
  if isinstance(operator, _ast.Mod):
    return '%'
  if isinstance(operator, _ast.Pow):
    return '**'
  if isinstance(operator, _ast.LShift):
    return '<<'
  if isinstance(operator, _ast.RShift):
    return '>>'
  if isinstance(operator, _ast.BitOr):
    return '|'
  if isinstance(operator, _ast.BitXor):
    return '^'
  if isinstance(operator, _ast.BitAnd):
    return '&'
  if isinstance(operator, _ast.FloorDiv):
    return '//'
  assert False


def expression_from_binop(ast_node):
  return MathExpression(expression_from_node(ast_node.left), operator_symbol_from_operator(ast_node.op),
                        expression_from_node(ast_node.right))


def expression_from_unaryop(ast_node):
  if isinstance(ast_node.op, _ast.Not):
    return NotExpression(expression_from_node(ast_node.operand))
  if isinstance(ast_node.op, _ast.UAdd):
    return expression_from_node(ast_node.operand)
  if isinstance(ast_node.op, _ast.USub):
    return MathExpression(LiteralExpression(-1), '*', expression_from_node(ast_node.operand))
  if isinstance(ast_node.op, _ast.Invert):
    # TODO: ~a.
    return UnknownExpression(astor.to_source(ast_node))


def operator_from_cmpop(cmpop):
  if isinstance(cmpop, _ast.Eq):
    return '=='
  if isinstance(cmpop, _ast.NotEq):
    return '!='
  if isinstance(cmpop, _ast.Lt):
    return '<'
  if isinstance(cmpop, _ast.LtE):
    return '<='
  if isinstance(cmpop, _ast.Gt):
    return '>'
  if isinstance(cmpop, _ast.GtE):
    return '>='
  if isinstance(cmpop, _ast.Is):
    return 'is'
  if isinstance(cmpop, _ast.IsNot):
    return 'is not'
  if isinstance(cmpop, _ast.In):
    return 'in'
  if isinstance(cmpop, _ast.NotIn):
    return 'not in'


def for_comprehension_from_comprehensions(comprehensions):
  # comprehension = (expr target, expr iter, expr* ifs, int is_async)
  last_comprehension = None
  for comprehension in comprehensions:
    target = expression_from_node(comprehension.target)
    iterator = expression_from_node(comprehension.iter)
    # TODO: !!!
    # comp_iters = [expression_from_node(if_) for if_ in comprehension.ifs]
    for_comprehension = ForComprehension(target, iterator, None)
    if last_comprehension:
      last_comprehension.comp_iter = for_comprehension
    last_comprehension = for_comprehension

  return last_comprehension


def comparison_expression_from_compare(ast_node):
  # (expr left, cmpop* ops, expr* comparators)
  # cmpop = Eq | NotEq | Lt | LtE | Gt | GtE | Is | IsNot | In | NotIn
  last_expression = ComparisonExpression(expression_from_node(ast_node.left),
                                         operator_from_cmpop(ast_node.ops[0]),
                                         expression_from_node(ast_node.comparators[0]))
  for cmpop, node in zip(ast_node.ops[1:], ast_node.comparators[1:]):
    last_expression = AndOrExpression(
        last_expression, 'and',
        ComparisonExpression(last_expression.right_expression, operator_from_cmpop(cmpop),
                             expression_from_node(node)))
  return last_expression


def kwargs_from_keywords(keywords):
  # -- keyword arguments supplied to call (NULL identifier for **kwargs)
  #   keyword = (identifier? arg, expr value)
  kwargs = None
  out = {}
  for arg, value in keywords:
    if arg is None:
      kwargs = StarredExpression('**', expression_from_node(value))
    else:
      out[arg] = expression_from_node(value)
  return kwargs, out


def expression_from_slice(ast_node):
  # slice = Slice(expr? lower, expr? upper, expr? step)
  #         | ExtSlice(slice* dims)
  #         | Index(expr value)
  if hasattr(ast_node, 'dims'):
    return ItemListExpression([expression_from_node(s) for s in ast_node.dims])
  if hasattr(ast_node, 'value'):
    return expression_from_node(ast_node.value)
  lower = expression_from_node(ast_node.lower) if hasattr(ast_node, 'lower') else None
  upper = expression_from_node(ast_node.upper) if hasattr(ast_node, 'upper') else None
  step = expression_from_node(ast_node.step) if hasattr(ast_node, 'step') else None
  return LiteralExpression(Slice(lower=lower, upper=upper, step=step))


def parse_from_ast(ast_node):
  return ParseNode(ast_node.lineno, ast_node.col_offset, native_node=ast_node)
