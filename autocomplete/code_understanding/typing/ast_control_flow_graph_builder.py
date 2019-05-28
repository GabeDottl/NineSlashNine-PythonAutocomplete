import ast

import _ast
import attr
from . import errors
from .control_flow_graph_nodes import (TypeHintStmtCfgNode, AssignmentStmtCfgNode, ExceptCfgNode, ExpressionCfgNode, ForCfgNode, FromImportCfgNode, FuncCfgNode, GroupCfgNode, IfCfgNode, ImportCfgNode, KlassCfgNode, LambdaExpression, ParseNode, ReturnCfgNode, TryCfgNode, WhileCfgNode, WithCfgNode, RaiseCfgNode)  # Temporary.
from .control_flow_graph_nodes import ModuleCfgNode
from .expressions import (InvertExpression, AndOrExpression, AttributeExpression, CallExpression, ComparisonExpression, DictExpression, ForComprehension, ForComprehensionExpression, IfElseExpression, ItemListExpression, KeyValueAssignment, KeyValueForComp, ListExpression, LiteralExpression, MathExpression, NotExpression, SetExpression, Slice, ExtSlice, IndexSlice, StarredExpression, SubscriptExpression, TupleExpression, VariableExpression, YieldExpression)  # Temporary.
from .language_objects import (Parameter, ParameterType)  # Temporary.
from ...nsn_logging import warning


@attr.s
class AstControlFlowGraphBuilder:
  module_loader = attr.ib()
  _module: 'Module' = attr.ib()
  root: GroupCfgNode = attr.ib(factory=GroupCfgNode)

  def graph_from_source(self, source, source_filename):
    try:
      ast_node = ast.parse(source)
    except SyntaxError as e:
      raise errors.AstUnableToParse(e)
    visitor = Visitor(self.module_loader, module=self._module, source_filename=source_filename, container_stack=[])
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
  module_loader = attr.ib()
  _module = attr.ib()
  source_filename: str = attr.ib()
  _container_stack = attr.ib(factory=list)
  root = attr.ib(None, init=False)
  _containing_func_node = None

  def new_group(self):
    group = GroupCfgNode()
    self.push(group)
    return ListPopper(self._container_stack, group.children)

  def generic_visit(self, ast_node):
    # TODO: verify if this is actually necessary - in theory, all should be wrapped in Expression.
    if isinstance(ast_node, EXPRESSIONS_TUPLE):
      return ExpressionCfgNode(expression_from_node(ast_node), parse_node=parse_from_ast(ast_node))
    super().generic_visit(ast_node)

  def visit_Module(self, ast_node):
    assert not self.root
    self.root = ModuleCfgNode()
    with ListPopper(self._container_stack, self.root.children):
      for stmt in ast_node.body:
        self.visit(stmt)

    assert not self._container_stack

  def visit_Interactive(self, ast_node):
    self.push(self._group_from_body(ast_node))

  def visit_Expression(self, ast_node):
    # expr body
    self.push(ExpressionCfgNode(expression_from_node(ast_node.body), parse_node=parse_from_ast(ast_node)))

  def visit_FunctionDef(self, ast_node):
    # (identifier name, arguments args, stmt* body, expr* decorator_list, expr? returns)
    suite = GroupCfgNode()
    old_containing_func = self._containing_func_node
    out = FuncCfgNode(
        ast_node.name,
        parameters_from_arguments(ast_node.args),
        suite,
        return_type_hint_expression=expression_from_node(ast_node.returns) if ast_node.returns else None,
        module=self._module,
        containing_func_node=old_containing_func,
        parse_node=parse_from_ast(ast_node))
    self._containing_func_node = out
    with ListPopper(self._container_stack, suite.children):
      for stmt in ast_node.body:
        self.visit(stmt)
    self._containing_func_node = old_containing_func
    self.push(out)

  def visit_AsyncFunctionDef(self, ast_node):
    # (identifier name, arguments args, stmt* body, expr* decorator_list, expr? returns)
    self.visit_FunctionDef(ast_node)

  def visit_ClassDef(self, ast_node):
    # (identifier name, expr* bases, keyword* keywords, stmt* body, expr* decorator_list)
    # TODO: Base classes.
    suite = GroupCfgNode()
    with ListPopper(self._container_stack, suite.children):
      for stmt in ast_node.body:
        self.visit(stmt)
    base_classes = [expression_from_node(base) for base in ast_node.bases]
    self.push(
        KlassCfgNode(ast_node.name,
                     base_classes,
                     suite,
                     module=self._module,
                     parse_node=parse_from_ast(ast_node)))

  def visit_Return(self, ast_node):
    # (expr? value)
    self.push(ReturnCfgNode(expression_from_node(ast_node.value), parse_node=parse_from_ast(ast_node)))

  def visit_Delete(self, ast_node):
    # (expr* targets)
    # TODO
    with self.new_group():
      for expr in ast_node.targets:
        self.push(ExpressionCfgNode(expression_from_node(expr), parse_node=parse_from_ast(ast_node)))

  def visit_Assign(self, ast_node):
    value_expression = expression_from_node(ast_node.value)
    parse_node = parse_from_ast(ast_node)
    for target in ast_node.targets:
      self.push(
          AssignmentStmtCfgNode(expression_from_node(target), '=', value_expression, parse_node=parse_node))

  def visit_AugAssign(self, ast_node):
    # (expr target, operator op, expr value)
    self.push(
        AssignmentStmtCfgNode(expression_from_node(ast_node.target),
                              f'{operator_symbol_from_operator(ast_node.op)}=',
                              expression_from_node(ast_node.value),
                              parse_node=parse_from_ast(ast_node)))

  def visit_AnnAssign(self, ast_node):
    # (expr target, expr annotation, expr? value, int simple)
    # 'simple' indicates that we annotate simple name without parens
    if not ast_node.value:
      self.push(TypeHintStmtCfgNode(expression_from_node(ast_node.target),
                              expression_from_node(ast_node.annotation),
                              parse_node=parse_from_ast(ast_node)))
    else:
      self.push(
          AssignmentStmtCfgNode(expression_from_node(ast_node.target),
                              '=',
                              expression_from_node(ast_node.value),
                              parse_node=parse_from_ast(ast_node),
                              type_hint_expression=expression_from_node(ast_node.annotation)))

  def _group_from_body(self, body):
    suite = GroupCfgNode()
    with ListPopper(self._container_stack, suite.children):
      for stmt in body:
        self.visit(stmt)
    return suite

  def visit_For(self, ast_node):
    # (expr target, expr iter, stmt* body, stmt* orelse) # use 'orelse' because else is a keyword in target languages
    suite = self._group_from_body(ast_node.body)
    else_suite = self._group_from_body(ast_node.orelse)
    self.push(
        ForCfgNode(expression_from_node(ast_node.target),
                   expression_from_node(ast_node.iter),
                   suite,
                   else_suite=else_suite,
                   parse_node=parse_from_ast(ast_node)))

  def visit_AsyncFor(self, ast_node):
    # (expr target, expr iter, stmt* body, stmt* orelse)
    self.visit_For(ast_node)

  def visit_While(self, ast_node):
    # (expr test, stmt* body, stmt* orelse)
    suite = self._group_from_body(ast_node.body)
    else_suite = self._group_from_body(ast_node.orelse)
    self.push(
        WhileCfgNode(expression_from_node(ast_node.test),
                     suite,
                     else_suite,
                     parse_node=parse_from_ast(ast_node)))

  def test_suite_from_if(self, ast_node):
    suite = self._group_from_body(ast_node.body)
    return expression_from_node(ast_node.test), suite

  def visit_If(self, ast_node):
    # (expr test, stmt* body, stmt* orelse)
    test_expression_tuples = [self.test_suite_from_if(ast_node)]
    for stmt in ast_node.orelse:
      if isinstance(stmt, _ast.If):
        test_expression_tuples.append(self.test_suite_from_if(stmt))
      else:
        suite = GroupCfgNode()
        with ListPopper(self._container_stack, suite.children):
          self.visit(stmt)
        test_expression_tuples.append((LiteralExpression(True), suite))

    self.push(IfCfgNode(test_expression_tuples, parse_node=parse_from_ast(ast_node)))

  def push(self, cfg_node):
    self._container_stack[-1].append(cfg_node)

  def visit_With(self, ast_node):
    # (withitem* items, stmt* body)
    # withitem = (expr context_expr, expr? optional_vars)
    suite = self._group_from_body(ast_node.body)
    # TODO: This is rather broken.
    with_exprs = []
    as_exprs = []
    for withitem in ast_node.items:
      with_exprs.append(expression_from_node(withitem.context_expr))
      if withitem.optional_vars:
        as_exprs.append(expression_from_node(withitem.optional_vars))
    self.push(
        WithCfgNode(ItemListExpression(with_exprs),
                    ItemListExpression(as_exprs),
                    suite,
                    parse_node=parse_from_ast(ast_node)))

  def visit_AsyncWith(self, ast_node):
    self.visit_With(ast_node)

  def visit_Raise(self, ast_node):
    # (expr? exc, expr? cause)
    self.push(RaiseCfgNode(
      exception=expression_from_node(ast_node.exc) if ast_node.exc else None,
      cause=expression_from_node(ast_node.cause) if ast_node.cause else None,
      parse_node=parse_from_ast(ast_node)))

  def visit_Try(self, ast_node):
    # (stmt* body, excepthandler* handlers, stmt* orelse, stmt* finalbody)
    # excepthandler = ExceptHandler(expr? type, identifier? name, stmt* body)
    suite = self._group_from_body(ast_node.body)
    else_suite = self._group_from_body(ast_node.orelse)
    finally_suite = self._group_from_body(ast_node.finalbody)
    except_nodes = []
    for except_handler in ast_node.handlers:
      except_nodes.append(
          ExceptCfgNode(
              expression_from_node(except_handler.type) if except_handler.type else None,
              VariableExpression(except_handler.name, parse_node=parse_from_ast(ast_node)) if except_handler.name else None,
              self._group_from_body(except_handler.body)))

    self.push(TryCfgNode(suite, except_nodes, else_suite, finally_suite))

  def visit_Assert(self, ast_node):
    # (expr test, expr? msg)
    # TODO
    self.push(ExpressionCfgNode(expression_from_node(ast_node.test), parse_node=parse_from_ast(ast_node)))

  def visit_Import(self, ast_node):
    # (alias* names)
    # alias = (identifier name, identifier? asname)
    for alias in ast_node.names:
      self.push(
          ImportCfgNode(alias.name,
                        as_name=alias.asname,
                        source_filename=self.source_filename,
                        module_loader=self.module_loader,
                        parse_node=parse_from_ast(ast_node)))

  def visit_ImportFrom(self, ast_node):
    # (identifier? module, alias* names, int? level)
    # alias = (identifier name, identifier? asname)
    self.push(
        FromImportCfgNode(f'{"."*ast_node.level}{ast_node.module}' if ast_node.module else '.' *
                          ast_node.level, {alias.name: alias.asname
                                           for alias in ast_node.names},
                          source_filename=self.source_filename,
                          module_loader=self.module_loader,
                          parse_node=parse_from_ast(ast_node)))

  def visit_Global(self, ast_node):
    # (identifier* names)
    # TODO
    self.generic_visit(ast_node)

  def visit_Nonlocal(self, ast_node):
    # (identifier* names)
    # TODO
    self.generic_visit(ast_node)

  def visit_Expr(self, ast_node):
    # (expr value)
    self.push(ExpressionCfgNode(expression_from_node(ast_node.value), parse_node=parse_from_ast(ast_node)))

  # def visit_Pass(self, ast_node):
  #   self.generic_visit(ast_node)

  # def visit_Break(self, ast_node):
  #   self.generic_visit(ast_node)

  # def visit_Continue(self, ast_node):
  #   self.generic_visit(ast_node)


def parameters_from_arguments(arguments):
  # arguments = (arg* args, arg? vararg, arg* kwonlyargs, expr* kw_defaults,
  #                arg? kwarg, expr* defaults)
  # arg = (identifier arg, expr? annotation)
  #         attributes (int lineno, int col_offset)
  out = []
  arg_iter = iter(arguments.args)
  for default, arg in zip(arguments.defaults, arg_iter):
    out.append(
        Parameter(arg.arg,
                  ParameterType.SINGLE,
                  default_expression=expression_from_node(default),
                  type_hint_expression=expression_from_node(arg.annotation) if arg.annotation else None))
  for arg in arg_iter:
    out.append(Parameter(arg.arg, ParameterType.SINGLE, type_hint_expression=expression_from_node(arg.annotation) if arg.annotation else None))
  if arguments.vararg:
    out.append(Parameter(arguments.vararg.arg, ParameterType.ARGS, type_hint_expression=expression_from_node(arguments.vararg.annotation) if arguments.vararg.annotation else None))
  kwarg_iter = iter(arguments.kwonlyargs)
  for default, arg in zip(arguments.kw_defaults, kwarg_iter):
    out.append(
        Parameter(arg.arg,
                  ParameterType.SINGLE,
                  default_expression=expression_from_node(default),
                  type_hint_expression=expression_from_node(arg.annotation) if arg.annotation else None))
  for arg in kwarg_iter:
    out.append(
        Parameter(arg.arg,
                  ParameterType.SINGLE,
                  type_hint_expression=expression_from_node(arg.annotation) if arg.annotation else None))
  if arguments.kwarg:
    out.append(Parameter(arguments.kwarg.arg, ParameterType.KWARGS, type_hint_expression=expression_from_node(arguments.kwarg.annotation) if arguments.kwarg.annotation else None))
  return out


def variables_from_targets(ast_nodes):
  return ItemListExpression([expression_from_node(ast_node) for ast_node in ast_nodes])


EXPRESSIONS_TUPLE = (_ast.BoolOp, _ast.BinOp, _ast.UnaryOp, _ast.Lambda, _ast.IfExp, _ast.Dict, _ast.Set,
                     _ast.ListComp, _ast.SetComp, _ast.DictComp, _ast.GeneratorExp, _ast.Await, _ast.Yield,
                     _ast.YieldFrom, _ast.Compare, _ast.Call, _ast.Num, _ast.Str, _ast.FormattedValue,
                     _ast.JoinedStr, _ast.Bytes, _ast.NameConstant, _ast.Ellipsis, _ast.Constant,
                     _ast.Attribute, _ast.Subscript, _ast.Starred, _ast.Name, _ast.List, _ast.Tuple)


def expression_from_node(ast_node):
  if ast_node is None:
    return LiteralExpression(None)

  assert isinstance(ast_node, EXPRESSIONS_TUPLE)
  if isinstance(ast_node, _ast.BoolOp):
    # (boolop op, expr* values)
    return expression_from_boolop(ast_node)
  if isinstance(ast_node, _ast.BinOp):
    # (expr left, operator op, expr right)
    return expression_from_binop(ast_node)
  if isinstance(ast_node, _ast.UnaryOp):
    # (unaryop op, expr operand)
    return expression_from_unaryop(ast_node)
  if isinstance(ast_node, _ast.Lambda):
    # (arguments args, expr body)
    parameters = parameters_from_arguments(ast_node.args)
    return LambdaExpression(parameters, expression_from_node(ast_node.body), parse_node=parse_from_ast(ast_node))
  if isinstance(ast_node, _ast.IfExp):
    # (expr test, expr body, expr orelse)
    return IfElseExpression(expression_from_node(ast_node.body), expression_from_node(ast_node.test),
                            expression_from_node(ast_node.orelse))
  if isinstance(ast_node, _ast.Dict):
    # (expr* keys, expr* values)
    value_iter = iter(ast_node.values)
    key_values = []
    for k, v in zip(ast_node.keys, ast_node.values):
      if k:
        key_values.append(KeyValueAssignment(expression_from_node(k), expression_from_node(v)))
      else:
        key_values.append(StarredExpression('**', expression_from_node(v)))

    return DictExpression(key_values)
  if isinstance(ast_node, _ast.Set):
    # (expr* elts)
    return SetExpression([expression_from_node(node) for node in ast_node.elts])
  if isinstance(ast_node, _ast.ListComp):
    # (expr elt, comprehension* generators)
    return ForComprehensionExpression(expression_from_node(ast_node.elt),
                                      for_comprehension_from_comprehensions(ast_node.generators))
  if isinstance(ast_node, _ast.SetComp):
    # (expr elt, comprehension* generators)
    return SetExpression([
        ForComprehensionExpression(expression_from_node(ast_node.elt),
                                   for_comprehension_from_comprehensions(ast_node.generators))
    ])
  if isinstance(ast_node, _ast.DictComp):
    # (expr key, expr value, comprehension* generators)
    return DictExpression([
        KeyValueForComp(expression_from_node(ast_node.key), expression_from_node(ast_node.value),
                        for_comprehension_from_comprehensions(ast_node.generators))
    ])
  if isinstance(ast_node, _ast.GeneratorExp):
    # (expr elt, comprehension* generators)
    return ForComprehensionExpression(expression_from_node(ast_node.elt),
                                      for_comprehension_from_comprehensions(ast_node.generators))
  if isinstance(ast_node, _ast.Await):
    # (expr value)
    # TODO
    return expression_from_node(ast_node.value)
  if isinstance(ast_node, _ast.Yield):
    # (expr? value)
    if ast_node.value:  # hasattr(ast_node, 'value'):
      return YieldExpression(expression_from_node(ast_node.value), False)
    return YieldExpression(None, False)
  if isinstance(ast_node, _ast.YieldFrom):
    # (expr value)
    # TODO: Generator
    return YieldExpression(expression_from_node(ast_node.value), True)
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
    return CallExpression(expression_from_node(ast_node.func),
                          args,
                          kwargs,
                          parse_node=parse_from_ast(ast_node))
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
    return ItemListExpression([expression_from_node(node) for node in ast_node.values])
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
    return AttributeExpression(expression_from_node(ast_node.value),
                               ast_node.attr,
                               parse_node=parse_from_ast(ast_node))
  if isinstance(ast_node, _ast.Subscript):
    # (expr value, slice slice, expr_context ctx)
    return SubscriptExpression(expression_from_node(ast_node.value),
                               expression_from_slice(ast_node.slice),
                               parse_node=parse_from_ast(ast_node))
  if isinstance(ast_node, _ast.Starred):
    # (expr value, expr_context ctx)
    return StarredExpression('*', expression_from_node(ast_node.value))
  if isinstance(ast_node, _ast.Name):
    # (identifier id, expr_context ctx)
    return VariableExpression(ast_node.id, parse_node=parse_from_ast(ast_node))
  if isinstance(ast_node, _ast.List):
    # (expr* elts, expr_context ctx)
    return ListExpression(variables_from_targets(ast_node.elts))
  if isinstance(ast_node, _ast.Tuple):
    # (expr* elts, expr_context ctx)
    return TupleExpression(variables_from_targets(ast_node.elts))
  warning(f'Unhandled Expression type {type(ast_node)}')
  assert False


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
  return MathExpression(expression_from_node(ast_node.left),
                        operator_symbol_from_operator(ast_node.op),
                        expression_from_node(ast_node.right),
                        parse_node=parse_from_ast(ast_node))


def expression_from_unaryop(ast_node):
  # expr operand
  if isinstance(ast_node.op, _ast.Not):
    return NotExpression(expression_from_node(ast_node.operand))
  if isinstance(ast_node.op, _ast.UAdd):
    return expression_from_node(ast_node.operand)
  if isinstance(ast_node.op, _ast.USub):
    return MathExpression(LiteralExpression(-1),
                          '*',
                          expression_from_node(ast_node.operand),
                          parse_node=parse_from_ast(ast_node))
  if isinstance(ast_node.op, _ast.Invert):
    # TODO: ~a.
    return InvertExpression(expression_from_node(ast_node.operand))


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
  for keyword in keywords:

    if keyword.arg is None:
      kwargs = StarredExpression('**', expression_from_node(keyword.value))
    else:
      out[keyword.arg] = expression_from_node(keyword.value)
  return kwargs, out


def expression_from_slice(ast_node):
  # slice = Slice(expr? lower, expr? upper, expr? step)
  #         | ExtSlice(slice* dims)
  #         | Index(expr value)
  if hasattr(ast_node, 'dims'):
    return ExtSlice([expression_from_slice(s) for s in ast_node.dims])
  if hasattr(ast_node, 'value'):
    return IndexSlice(expression_from_node(ast_node.value))
  lower = expression_from_node(ast_node.lower) if ast_node.lower else None
  upper = expression_from_node(ast_node.upper) if ast_node.upper else None
  step = expression_from_node(ast_node.step) if ast_node.step else None
  return Slice(lower=lower, upper=upper, step=step)


def parse_from_ast(ast_node):
  return ParseNode(ast_node.lineno, ast_node.col_offset, native_node=ast_node)
