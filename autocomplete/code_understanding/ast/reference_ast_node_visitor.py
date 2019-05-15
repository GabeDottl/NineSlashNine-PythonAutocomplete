import ast
import importlib

import _ast
from autocomplete.code_understanding.ast.ast_utils import _name_id_or_arg
from autocomplete.code_understanding.builtins import builtins, module_members
from autocomplete.code_understanding.utils import *
from autocomplete.nsn_logging import *


class ReferenceAstNodeVisitor(ast.NodeVisitor):
  '''An ReferenceAstNodeVisitor per-module.'''

  def __init__(self, module_path, module_source=None, module_path_to_traveler=None):
    if module_path_to_traveler is None:
      self.module_path_to_traveler = {}
    else:
      self.module_path_to_traveler = module_path_to_traveler
    assert module_path is not None
    # Wish I could auto-convert all of these to private members...
    self.module_path = module_path
    self.module_source = module_source
    self.module_ast = None
    self.module_name = get_module_name_from_filepath(self.module_path)
    # self.current_module_name = ''
    self.nodes = []
    self.node_to_parent = {}
    self.current_context = ''
    self.parent = None
    self.names_to_node = {}
    self.current_local_names = []
    self.current_enclosing_names = []
    self.current_global_names = []
    self.current_instance_names = []
    self.references = []

  def _load_source(self):
    if self.module_source is None:
      with open(self.module_path) as f:
        self.module_source = ''.join(f.readlines())

  def get_references(self):
    self._load_source()
    lines = source.splitlines()
    out = []
    for reference in self.references:
      out.append((*reference, lines[int(reference[-1] - 1)]))
    return out

  def get_reference_counts(self):
    counts = {}
    for reference in self.references:
      if reference[1] in counts:
        counts[reference[1]] += 1
      else:
        counts[reference[1]] = 1
    return counts

  def traverse(self):
    self._load_source()
    self.module_ast = ast.parse(self.module_source)
    self.generic_visit(self.module_ast)

  def _extract_fields(self, node):
    type_name_ = type_name(node)
    if isinstance(node, _ast.Module):
      name = self.module_name
    else:
      name = _name_id_or_arg(node)
    lineno = node.lineno if hasattr(node, 'lineno') else None
    # parent_name = self.parent.name if hasattr(self.parent, 'name') else None
    return type_name_, name, lineno

  def generic_visit(self, node):
    '''Do not call directly - call traverse.'''
    # try:
    # Only do stuff for the types of nodes that effect defining and using names.
    if not isinstance(node, (_ast.Module, _ast.Assign, _ast.Import, _ast.ImportFrom, _ast.FunctionDef,
                             _ast.ClassDef, _ast.arg, _ast.alias, _ast.Name, _ast.Attribute)):
      super(ReferenceAstNodeVisitor, self).generic_visit(node)
      return

    # Extract some generic fields and add them all to self.nodes.
    type_name_, name, lineno = self._extract_fields(node)
    complete_name = join_names(self.current_context, name)  #_complete_name(node, self.node_to_parent)
    if complete_name is not None:
      # print(f'Complete name for {name}{lineno}: {complete_name}')
      self.names_to_node[complete_name] = node
    self.nodes.append((type_name_, name, complete_name, lineno, node, self.parent))
    assert not node == self.parent
    if node not in self.node_to_parent:
      self.node_to_parent[node] = self.parent
    else:
      print(
          f'{node} has existing parent {_name_id_or_arg(self.node_to_parent[node])} compared to {_name_id_or_arg(self.parent)}'
      )

    # If the node is a function, then any variables defined within should
    # fall out of scope. Otherwise, they'll stay.
    # https://www.geeksforgeeks.org/scope-resolution-in-python-legb-rule/
    # Alias | Complete Name* | Type | Params (for functions)
    # _ast.Assign, _ast.Import, _ast.FunctionDef, _ast.ClassDef, _ast.arg, _ast.alias, _ast.Name, _ast.Attribute
    if isinstance(node, (_ast.ClassDef, _ast.FunctionDef)):
      # In case this is a nested class, keep track of old vals.
      # outter_instance_vals = self.current_instance_names
      # self.current_instance_names = []

      # For the purposes of ordering, current locals should be moved into enclosing.
      old_enclosing = self.current_enclosing_names
      self.current_local_names.insert(0, (name, complete_name, type_name_))
      old_local = self.current_local_names
      self.current_enclosing_names = self.current_enclosing_names + self.current_local_names
      self.current_local_names = []

    elif isinstance(node, _ast.arg):
      # Add arguments to the function's locals - this will get wiped when
      # finishing with the function
      self.current_local_names.insert(0, (name, complete_name, type_name_))

    elif isinstance(node, _ast.Import):
      self._handle_import(node)
      return

    elif isinstance(node, _ast.ImportFrom):
      self._handle_import_from(node)
      return

    elif isinstance(node, _ast.Assign):
      self._handle_assign(node)
      return

    elif isinstance(node, (_ast.Name, _ast.Attribute)):
      # Note: This will miss Names & Attributes contained in Imports and
      # Assign[ment]s since the children of those nodes are handled directly.
      if isinstance(node, _ast.Attribute):
        name = _get_complete_attribute_path(node)
      else:
        name = node.id
      self.references.append((name, self._find_matching_name(node), self.current_context, lineno))

    elif isinstance(node, _ast.Module):
      old_global = self.current_global_names
      module_names = []
      for module_name in module_members:
        module_names.insert(0, (module_name, join_names(name, module_name), 'Unknown'))
      self.current_global_names = module_names + old_global

    #Figure out remainder of logic aroung LEBG +_find_matching_name
    old_parent = self.parent
    self.parent = node
    old_context = self.current_context
    self.current_context = complete_name
    super(ReferenceAstNodeVisitor, self).generic_visit(node)
    self.parent = old_parent
    self.current_context = old_context

    if isinstance(node, _ast.Module):
      self.current_global_names = old_global

    elif isinstance(node, (_ast.ClassDef, _ast.FunctionDef)):
      # In case this is a nested class, restore old vals.
      # self.current_instance_names = outter_instance_vals
      # TODO### Add this to
      self.current_enclosing_names = old_enclosing
      if isinstance(node, _ast.ClassDef):
        # If it's a class, keep the things around but with full names.
        for local_name, local_complete_name, local_type_name in self.current_local_names[::-1]:
          old_local.insert(0, (join_names(name, local_name), local_complete_name, local_type_name))
      self.current_local_names = old_local

  def _find_matching_name(self, node):
    if isinstance(node, _ast.Attribute):
      name = _get_complete_attribute_path(node)
    else:
      assert isinstance(node, _ast.Name), type_name(node)
      name = node.id
    for name_list in (self.current_local_names, self.current_enclosing_names, self.current_instance_names,
                      self.current_global_names):
      # TODO: For instance names, prepend 'self.' to each for matching here.
      for node_name_tuple in name_list:
        if node_name_tuple[0] == name:
          return node_name_tuple[1]  # complete_name
    # Note that this must come below the above due to LEGB ordering.
    if name in builtins:
      return name
    return None

  def _handle_assign(self, node):
    self.generic_visit(node.value)
    for target in node.targets:
      # assert isinstance(target, _ast.Name)
      if isinstance(target, _ast.Name):
        self.current_local_names.insert(
            0, (target.id, join_names(self.current_context, target.id), type_name(node)))
      else:
        assert isinstance(target, _ast.Attribute), f'{type(target)}'
        name = _get_complete_attribute_path(target)
        self.current_local_names.append((name, name, type_name(node)))

  def _handle_import(self, node):
    for name_alias in node.names:  # Each name is an _ast.alias.
      assert isinstance(name_alias, _ast.alias), f'{type(name_alias)}'
      name = name_alias.asname if name_alias.asname is not None else name_alias.name
      self._process_module(name_alias.name)
      self.current_local_names.append((name, name_alias.name, type_name(node)))

  def _handle_import_from(self, node):
    for name_alias in node.names:  # Each name is an _ast.alias.
      assert isinstance(name_alias, _ast.alias), f'{type(name_alias)}'
      name = name_alias.asname if name_alias.asname is not None else name_alias.name
      if name is '*':
        traveler = self._process_module(node.module)
        # Blegh.
        self.current_local_names += traveler.current_local_names
        # for module_local_name in traveler.current_local_names:
        #   self.current_local_names.append()
      else:
        self.current_local_names.append((name, join_names(node.module, name_alias.name), type_name(node)))

  def _process_module(self, module_name):
    module_spec = importlib.util.find_spec(module_name)
    if module_spec.origin is None:
      # Probably a builtin - just load the module and inspect it instead as a
      # fallback.
      module = module_spec.loader.load_module(module_name)
      module_locals = list(lambda x: x[0] != '_', dir(module))
    full_module_path = module_spec.origin

    assert full_module_path is not None, f'Could not get module path for {module_name}'
    module_path = os.path.relpath(full_module_path)
    assert module_path is not None
    if module_path in self.module_path_to_traveler:
      return self.module_path_to_traveler[module_path]
    else:
      traveler = ReferenceAstNodeVisitor(module_path=module_path,
                                         module_path_to_traveler=self.module_path_to_traveler)
      self.module_path_to_traveler[module_path] = traveler
      traveler.traverse()
    return traveler
