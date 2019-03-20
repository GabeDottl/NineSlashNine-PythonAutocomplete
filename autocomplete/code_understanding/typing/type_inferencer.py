import parso
import attr


@attr.s
class Type:
  type_ = attr.ib()
  is_ambiguous = attr.ib(default=False)
  value = attr.ib(default=None)


@attr.s
class TypeOf:
  expr = attr.ib()


@attr.s
class ComplexType:
  '''Class for types that are too complex to extrapolate.'''
  code = attr.ib()


class UnknownType:
  '''Types that are unknown.'''


@attr.s
class IndexOf:
  array = attr.ib()
  index = attr.ib()


class ResultOf:

  def __init__(self, call, *args, **kwargs):
    self.call = call
    self.args = args
    self.kwargs = kwargs

@attr.s
class ImportOf:
  path= attr.ib()

@attr.s
class ImportFrom:
  path= attr.ib(kw_only=True)
  name = attr.ib(kw_only=True)
  as_name = attr.ib(kw_only=True)
# @attr.s
# class TypeOf:
#   name = attr.ib()

# @attr.s
# class InstanceOf:
#   type = attr.ib()
#
# class :
#   '''An  is either a reference referring to value or a value itself.
#   This is the base-class of Reference and TempValue.
#   '''


@attr.s
class Reference:
  name = attr.ib(kw_only=True)
  scope = attr.ib(kw_only=True)
  # unknown = attr.ib(False)
  temp = attr.ib(False, kw_only=True)
  assignments = []


  def get_complete_name(self):
    out = []
    scope = self.scope
    while scope:
      out.insert(0, scope.name)
      scope = scope.scope
    out.append(self.name)
    return ''.join(out)

@attr.s
class IndexReference:
  source_reference = attr.ib(kw_only=True)
  index = attr.ib(kw_only=True)
  assignments = []


@attr.s
class ReferenceAssignment:
  reference = attr.ib(kw_only=True)
  pos = attr.ib(kw_only=True)
  value = attr.ib(kw_only=True)


# class TempReference:
# name = attr.ib()
# value =

# @attr.s
# class TempValue():
#   pos = attr.ib()
#   type = attr.ib()

# class NotReferenceDefinitionException(Exception):
#   '''Exception raised when a node is not defining an reference.'''

# def eval_order(node):
#   if node.type == 'simple_stmt':
#     return 0
#   return 1


class TypeInferencer:
  references_dict = {}
  current_scope_path = []

  def reference_exists(self, name):
    return name in self.references_dict

  def find_reference(self, name):
    # TODO: Scoping!
    return self.references_dict[name]

  def add_reference(self, name, reference):
    # TODO: Scoping!
    self.references_dict[name] = reference

  def typify_tree(self, node):
    # Here, we essentially handle the higher-level nodes we might encounter
    # which are very generic.
    if node.type == 'newline' or node.type == 'endmarker' or node.type == 'keyword':
      return
    if node.type == 'import_name':
      self.handle_import_name(node)
    elif node.type == 'import_from':
      self.handle_import_from(node)
    elif node.type == 'classdef':
      self.handle_classdef(node)
    elif node.type == 'funcdef':
      self.handle_funcdef(node)
    elif node.type == 'decorated':
      # TODO: Handle decorators.
      self.typify_tree(node.children[1]) # node.children[0] is a decorator.
    elif node.type == 'async_stmt':
      self.typify_tree(node.children[1]) # node.children[0] is 'async'.
    elif node.type == 'if_stmt':
      self.handle_if_stmt(node)
    elif node.type == 'simple_stmt':
      self.handle_simple_stmt(node)
    elif node.type == 'expr_stmt':
      self.handle_expr_stmt(node)
    elif node.type == 'for_stmt':
      self.handle_for_stmt(node)
    elif node.type == 'while_stmt':
      self.handle_while_stmt(node)
    elif node.type == 'try_stmt':
      self.handle_try_stmt(node)
    elif node.type == 'with_stmt':
      self.handle_with_stmt(node)
    else:
      assert False, node_info(node)

  def handle_import_name(self, node):
    # import_name: 'import' dotted_as_names
    # dotted_as_names: dotted_as_name (',' dotted_as_name)*
    # dotted_as_name: dotted_name ['as' NAME]
    # dotted_name: NAME ('.' NAME)*
    child = node.children[1] # 0 is 'import'
    if child.type == 'dotted_as_name':
      self.import_dotted_as_name(child)
    else:
      assert child.type == 'dotted_as_names', node_info(child)
      # some combination of
      for child in dotted_as_names:
        if child.type == 'name':
          self.create_import_reference(child, child.value)
        elif child.type == 'operator':
          assert child.value == ',', node_info(child)
        else:
          assert child.type == 'dotted_as_name', node_info(child)
          self.import_dotted_as_name(child)


  def create_import_reference(self, node, path, from_import_name=None, as_name=None):
    # assert not (from_import_name and as_name), (from_import_name, as_name)
    if as_name is not None:
      name = as_name
    elif from_import_name is not None:
      name = from_import_name
    else:
      name = path

    reference = Reference(name=name, scope=self.current_scope_path[-1])
    if from_import_name and as_name:
      assignment = ReferenceAssignment(reference=reference, pos=node.start_pos, value=ImportFrom(path=path, name=from_import_name, as_name=as_name))
    elif from_import_name:
      assignment = ReferenceAssignment(reference=reference, pos=node.start_pos, value=ImportFrom(path=path, name=from_import_name, as_name=from_import_name))
    else:
      assignment = ReferenceAssignment(reference=reference, pos=node.start_pos, value=ImportOf(path))
    reference.assignments.append(assignment)
    self.add_reference(as_name, reference)


  def import_dotted_as_name(self, node):
    assert node.type == 'dotted_as_name', node_info(node)
    if node.children[0].type == 'name':
      path = node.children[0].value
    else:
      dotted_name = node.children[0]
      assert dotted_name.type == 'dotted_name', node_info(dotted_name)
      path = ''.join([child.value for child in dotted_name.children])
    if len(node.children) == 1: # import x
      self.create_import_reference(node, path)
    else:
      assert len(node.chilren) == 3, node_info(node) # import a as b
      self.create_import_reference(node, path, node.children[-1].value)

  def handle_import_from(self, node):
    # import_from: ('from' (('.' | '...')* dotted_name | ('.' | '...')+)
    #              'import' ('*' | '(' import_as_names ')' | import_as_names))
    # import_as_name: NAME ['as' NAME]
    # from is first child
    path_node_index = 1
    # First node after import might be '.' or '...' operators.
    path_node = node.children[path_node_index]
    path = ''
    if path_node.type == 'operator':
      path = path_node.value
      path_node_index +=1
      path_node = node.children[path_node_index]

    if path_node.type == 'name':
      path += path_node.value
    else:
      assert path_node.type == 'dotted_name', node_info(path_node)
      path += ''.join([child.value for child in path_node.children])
    # import is next node
    import_as_names = node.children[path_node_index + 2]
    if import_as_names.type == 'operator': # from x import (y)
      import_as_names = node.children[path_node_index + 3]
    if import_as_names.type == 'name':
      self.create_import_reference(node, path, from_import_name=import_as_names.value)
    else:
      assert import_as_names.type == 'import_as_names', node_info(import_as_names)
      for child in import_as_names.children:
        if child.type == 'name':
          self.create_import_reference(node, path, from_import_name=child.value)
        elif child.type == 'operator':
          assert child.value == ',', node_info(node)
        else:
          assert child.type == 'import_as_name', node_info(child)
          assert len(child.children) == 3, node_info(child)
          self.create_import_reference(node, path, from_import_name=child.children[0].value,  as_name=child.children[-1].value)


  def handle_classdef(self, node):
    reference = self._create_reference_and_assignment(node)
    self.current_scope_path.append(reference)
    # [keyword, name, operator] = class X: - skip these.
    for child in node.children[3:]:
      typify_tree(child)
    self.current_scope_path.pop()

  def handle_funcdef(self, node):
    reference = self._create_reference_and_assignment(node)
    self.current_scope_path.append(reference)
    # [keyword, name, parameters, operator, suite] = def foo(): suite
    assert len(node.children) == 5, node.get_code()
    self.handle_parameters(node.children[2])
    self.handle_suite(node.children[4])
    self.current_scope_path.pop()

  def handle_parameters(self, node):
    assert node.type == 'parameters', node_info(node)
    # First, positional or kwargs, then optionally *args, more kwargs, **kwargs
    # if len(node.children == 2):
    #   return # just ().

    # TODO: Handle self?
    # Don't really need to worry about things like *args, **kwargs, etc. here.
    for param_node in node.children[1:-1]: # skip operators on either end.
      assert param_node.type == 'param', (param_node.type, param_node.get_code())
      reference = Reference(param.name.value, scope=self.current_scope_path[-1])
      self.add_reference(param.name.value, reference)

  def handle_suite(self, node):
    assert node.type == 'suite', node_info(node)
    for child in node.children:
      self.typify_tree(node)

  def handle_simple_stmt(self, node):
    for child in node.children:
      self.typify_tree(child)

  def handle_expr_stmt(self, node):
    # Essentially, these are assignment expressions and can take a few forms:
    # a = b, a: List[type] = [...]
    # a,b = 1,2 or a,b = foo()
    # So, we need to handle essentially 1 or more things on the left and right
    # and possibly ignore a type hint in the assignment.
    testlist_star_expr = node.children[0]
    # if testlist_star_expr.type == 'name':
    #   names = (testlist_star_expr.value,)
    # else:
    names = self.extract_references_from_testlist_star_expr(testlist_star_expr)
    if len(node.children) == 2:
      annasign = node.children[1]
      assert annasign.type == 'annassign', node_info(node)
      results = annasign.children[-1]
    else:
      assert len(node.children) == 3, node_info(node)
      results = node.children[-1]
    results = self.extract_values(results)
    # 1 or more things that we


  def extract_references_from_testlist_star_expr(self, node):
    if node.type == 'name': # Simplest case - a=1
      if self.reference_exists(node.value):
        return self.find_reference(node.value)
      else:
        reference = Reference(name=node.value, scope=self.current_scope_path[-1])
        self.add_reference(node.value, reference)
        return reference
    elif node.type == 'testlist_star_expr':
      out = []
      for child in node.children:
        out.append(self.extract_references_from_testlist_star_expr(child))
      return out
    elif node.type == 'atom':
      child = node.children[0]
      if child.type == 'operator':
        assert len(node.children) == 3, node_info(node)
        if child.value == '(' or child.value == '[':
          return self.extract_references_from_testlist_star_expr(child.children[1])
        else:
          assert False, node_info(child)
      else:
        assert child.type == 'name', node_info(child)
        return self.extract_references_from_testlist_star_expr(child)
    elif child.type == 'atom_expr':




    # atom, testlist_comp, atom_expr, trailer, name
    pass

  def extract_reference_from_atom_expr(self, node):
    # atom_expr: ['await'] atom trailer*
    iterator = iter(node.children)
    reference_node = next(iterator)
    # Might be 'await' instead of an actual reference_node - fastforward if so.
    if reference_node.type == 'keyword' and reference_node.value == 'await':
      reference_node = next(iterator)

    last_reference = node_to_reference_or_value(reference_node)
    previous_name = None
    # trailer: '(' [arglist] ')' | '[' subscriptlist ']' | '.' NAME
    for trailer in iterator:
      if trailer.children[0].value == '(':
        # TODO: func call
        last_reference = Reference(name='temp', scope=last_reference, temp=True)
        # TODO: Handle function args.
        last_reference.assignments.append(
            ReferenceAssignment(
                reference=last_reference,
                pos=trailer.start_pos,
                value=ResultOf(self.find_reference(previous_name))))
        previous_name = None
      elif trailer.children[0].value == '[':
        # TODO: array access
        # TODO: func call
        last_reference = Reference(name='temp', scope=last_reference, temp=True)
        # TODO: Handle index params.
        last_reference.assignments.append(
            ReferenceAssignment(
                reference=last_reference,
                pos=trailer.start_pos,
                value=IndexOf(self.find_reference(previous_name), 0)))
        previous_name = None
      else:
        # TODO: handle previous node as reference
        assert trailer.children[0].value == '.', trailer.get_code()
        if previous_name:
          new_reference = Reference(name=previous_name, scope=last_reference)
        previous_name = trailer.children[1].value  # name
    if previous_name:
      new_reference = Reference(name=previous_name, scope=last_reference)


  def extract_values(self, node):
    pass

  def handle_for_stmt(self, node):
    for child in node.children:
      pass

  def handle_while_stmt(self, node):
    for child in node.children:
      pass

  def handle_try_stmt(self, node):
    for child in node.children:
      pass

  def handle_with_stmt(self, node):
    for child in node.children:
      pass


  def _create_reference_and_assignment(self, node):
    reference = Reference(name=node.name.value, scope=self.current_scope_path[-1])
    self.add_reference(node.name.value,  reference)
    reference_assignment = ReferenceAssignment(
        reference=reference, pos=node.start_pos, value=node.type)
    reference.assignments.append(reference_assignment)
    return reference

  def insert_name_types(self, node):
    # print(node)
    if node.type == 'classdef' or node.type == 'funcdef':
      pass
    elif node.type == 'expr_stmt' and children_contains_operator(node, '='):
      # print(node)
      left = node.children[0]
      right = node.children[2]
      results = eval_type(right)
      # TODO: Be more robust? E.g. a, (b,c).
      reference_assignments = get_reference_assignments(left)
      if len(reference_assignments) == 1:
        reference_assignments[0].type = results
      elif not isinstance(results, (tuple, list)):
        for i, reference_assignment in enumerate(reference_assignments):
          reference_assignment.type = IndexOf(results, i)
      else:
        for reference_assignment, result in zip(reference_assignments, results):
          reference_assignment.type = result

  def get_reference_assignments(self, node, first=True):
    reference = None
    if node.type == 'name':
      if self.reference_exists(node.value):
        reference = self.find_reference(node.value)
      else:
        reference = Reference(name=node.value, scope=scope)
        self.add_reference(node.value, reference)

    if node.type == 'atom_expr':
      reference = atom_expr_to_atom(node)

    if reference is not None:
      reference_assignment = ReferenceAssignment(
          reference=reference, pos=node.start_pos, value=None)
      reference.assignments.append(reference_assignment)
      return (reference_assignment,) if first else reference_assignment
    out = []
    try:
      for child in node.children:
        reference_assignments = get_reference_assignments(
            child, first=False)
        if reference_assignments:
          out.append(reference_assignments)
    except AttributeError:
      pass
    return out

  # def temp_name(self,node):
  #   return f'{node.start_pos}: {node.get_code()}'



  def node_to_reference_or_value(self, node):
    if hasattr(node, 'name'):
      return self.find_reference(node.name)
    else:
      reference = Reference(name='temp', scope=None, temp=True)
      ReferenceAssignment(
          reference=reference,
          pos=node.start_pos,
          value=eval_type(node))
      return
      # self.references_dict[temp_name(node)] = reference
    # return reference

  def eval_type(self, node):
    if node.type == 'name':
      return TypeOf(self.find_reference(node.value))
    if node.type == 'number' or node.type == 'str':
      return Type(node.type)
    return ComplexType(node.get_code())


def children_contains_operator(node, operator_str):
  for child in node.children:
    if child.type == 'operator' and child.value == operator_str:
      return True
  return False


def path_to_name(node, name):
  try:
    if node.value == name:
      return (node,)
  except AttributeError:
    pass
  try:
    for child in node.children:
      x = path_to_name(child, name)
      if x is not None:
        return (node, *x)
  except AttributeError:
    pass
  return None

def node_info(node):
  return (node.type, node.get_code())


def extract_nodes_of_type(node, type_, out=None):
  if out is None:
    out = []
  if node.type == type_:
    out.append(node)
  try:
    for child in node.children:
      extract_nodes_of_type(child, type_, out)
  except AttributeError:
    pass
  return out
