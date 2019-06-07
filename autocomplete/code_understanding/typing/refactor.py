import os
from abc import ABC
from collections import OrderedDict, defaultdict
from itertools import chain
from typing import List, abstractmethod

import attr

import _ast

from . import api, control_flow_graph_nodes, expressions
from ...nsn_logging import info


@attr.s
class ModuleImportChange:
  cfg_node = attr.ib()
  inserts = attr.ib()
  deletes = attr.ib()


def create_import_changes(source: str, changes: List[ModuleImportChange]) -> str:
  # Otherwise, we're essentially recreating an arbitrary
  new_source = source
  # Turn this into a dict so we can delete from it without shifting lines.
  new_source_lines = OrderedDict()
  for i, l in enumerate(source.splitlines()):
    new_source_lines[i] = l

  replacements = []
  inserts = []
  deletes = []

  # TODO: Migrate this to apply_insert_and_deletes func & merge with create_import_inserts.
  for change in changes:
    parso_node = change.cfg_node.parse_node.native_node
    assert not isinstance(parso_node, _ast.AST), "Must create graph w/parso."
    if isinstance(change.cfg_node, control_flow_graph_nodes.ImportCfgNode):
      assert not change.inserts
      assert len(change.deletes) == 1
      deletes.append(delete(pchange.cfg_node.parse_node.get_range()))
      # for i in range(parso_node.start_pos[0], parso_node.end_pos[0] + 1):
      #   del new_source_lines[i - 1]
      continue

    if not change.inserts and len(change.deletes) == len(change.cfg_node.from_import_name_alias_dict):
      # Removing the entire from_import
      deletes.append(delete(change.cfg_node.parse_node.get_range()))
      # for i in range(parso_node.start_pos[0], parso_node.end_pos[0] + 1):
      #   del new_source_lines[i - 1]
    else:
      new_from_imports = set(add for add in change.inserts)
      deletes = set(change.deletes)
      for value, as_name in change.cfg_node.from_import_name_alias_dict.items():
        if value not in deletes:
          new_from_imports.add((value, as_name))

      start_pos, end_pos = change.cfg_node.parse_node.extras
      change_range = control_flow_graph_nodes.ParseNode.get_range_from_parso_start_end(
          *change.cfg_node.parse_node.extras)
      # if start_pos[0] == end_pos[0]:  # Same lin
      #   line = new_source_lines[start_pos[0] - 1]
      #   line = f'{line[:start_pos[1]]}{line[end_pos[1]:]}'
      # else:
      #   line = new_source_lines[start_pos[0] - 1][:start_pos[1]]
      #   for lineno in range(start_pos[0], end_pos[0]):
      #     del new_source_lines[lineno]

      # insertion_col = start_pos[1]
      if len(new_from_imports) >= 1:
        if len(new_from_imports) > 1:
          new_from_imports = sorted(new_from_imports, key=lambda from_as_name: from_as_name[0])
          insertion = f'({", ".join(import_format(v,a) for v,a in new_from_imports)})'
        else:
          insertion = f'{", ".join(import_format(v,a) for v,a in new_from_imports)}'
        replacements.append(Replace(*change_range, insertion))
        # line = f'{line[:insertion_col]}{insertion}{line[insertion_col:]}'
        # new_source_lines[start_pos[0] - 1] = line
  # The above approach strips the new-line at the end with splitlines - readd.
  return replacements, inserts, deletes


def import_format(value, as_name):
  if as_name:
    return f'{value} as {as_name}'
  return value


def create_import_inserts(source, source_filename, fixes):
  if not fixes:
    return []

  graph = api.graph_from_source(source, source_filename, parso_default=True)
  module_to_value_dict = defaultdict(list)

  module_imports = []
  for fix in fixes:
    module_name, value = fix.get_module_name_and_value(os.path.dirname(source_filename))
    if not value:
      module_imports.append((module_name, fix.as_name))
    else:
      module_to_value_dict[module_name].append((value, fix.as_name))

  inserts = []
  first_node = graph.children[0]
  if module_imports:
    import_nodes = list(graph.get_descendents_of_types(control_flow_graph_nodes.ImportCfgNode))

    if not import_nodes:
      if isinstance(first_node, control_flow_graph_nodes.ExpressionCfgNode) and isinstance(
          first_node.expression, expressions.LiteralExpression) and isinstance(
              first_node.expression.literal, str):
        # First node is a module comment! Insert imports after it.
        import_insertion_line = first_node.parse_node.native_node.end_pos[0]
      else:
        import_insertion_line = 0
      for module, as_name in reversed(sorted(module_imports)):
        inserts.append(Insert((import_insertion_line, 0), f'import {import_format(module, as_name)}\n'))
      # Last thing inserted will be inserted first.
      if import_insertion_line != 0:
        inserts.append(Insert((import_insertion_line, 0), '\n'))
    else:
      import_nodes = sorted(import_nodes, key=lambda node: node.module_path)
      for module_name, as_name in sorted(module_imports):
        if import_nodes[0].module_path > module_name:
          import_insertion_line = import_nodes[0].parse_node.lineno - 1
        else:
          for node in import_nodes:
            if node.module_path > module_name:
              import_insertion_line = node.parse_node.lineno - 1
              break
          else:
            import_insertion_line = import_nodes[-1].parse_node.parso_node.end_pos[0]

        inserts.append(Insert((import_insertion_line, 0), f'import {import_format(module_name, as_name)}\n'))

  if module_to_value_dict:
    from_import_nodes = list(graph.get_descendents_of_types(control_flow_graph_nodes.FromImportCfgNode))
    if not from_import_nodes:
      import_nodes = list(graph.get_descendents_of_types(control_flow_graph_nodes.ImportCfgNode))
      from_insertion_line = 0
      if import_nodes:
        end_of_inserts = 0
        for n in import_nodes:
          node_end_line = n.parse_node.native_node.end_pos[0]
          if node_end_line > end_of_inserts:
            end_of_inserts = node_end_line
        from_insertion_line = end_of_inserts + 1
        inserts.append(Insert((from_insertion_line, 0), '\n'))
      else:
        if inserts:
          from_insertion_line = import_insertion_line + 1
          inserts.append(Insert((from_insertion_line, 0), '\n'))
        elif isinstance(first_node, control_flow_graph_nodes.ExpressionCfgNode) and isinstance(
            first_node.expression, expressions.LiteralExpression) and isinstance(
                first_node.expression.literal, str):
          # First node is a module comment! Insert imports after it.
          from_insertion_line = first_node.parse_node.native_node.end_pos[0]
          inserts.append(Insert((from_insertion_line, 0), '\n'))

      # TODO: Relative imports first, new-line, absolute.
      for module_name, values in reversed(sorted(module_to_value_dict.items())):
        if len(values) > 1:
          inserts.append(
              Insert((
                  from_insertion_line, 0
              ), f'from {module_name} import ({", ".join([import_format(v, a) for v, a in sorted(values)])})\n'
                     ))
        else:
          inserts.append(
              Insert((from_insertion_line, 0), f'from {module_name} import {import_format(*values[0])}\n'))
    else:  # Existing from_imports.
      from_import_nodes = sorted(from_import_nodes, key=lambda node: node.module_path)
      for module_name, values in reversed(sorted(module_to_value_dict.items())):
        if from_import_nodes[0].module_path > module_name:
          from_insertion_line = from_import_nodes[0].parse_node.lineno - 1
        else:
          for node in from_import_nodes:
            if node.module_path > module_name:
              from_insertion_line = node.parse_node.lineno - 1
              break
          else:
            # Insert after all other from_imports.
            from_insertion_line = from_import_nodes[-1].parse_node.native_node.end_pos[0]
        if len(values) > 1:
          inserts.append(
              Insert((
                  from_insertion_line, 0
              ), f'from {module_name} import ({", ".join([import_format(v, a) for v, a in sorted(values)])})\n'
                     ))
        else:
          inserts.append(
              Insert((from_insertion_line, 0), f'from {module_name} import {import_format(*values[0])}\n'))

  info(f'inserts: {inserts}')
  return inserts


@attr.s
class Change(ABC):
  # @abstractmethod
  # def to_dict(self):
  #   ...
  @abstractmethod
  def get_end_pos(self):
    ...

  @abstractmethod
  def sort_pos(self):
    ...
  
  @staticmethod
  def relative_pos(pos, lines):
    if pos[1] < 0:
      return pos[0], len(lines[pos[0]]) + pos[1]
    return pos


@attr.s
class Replace(Change):
  start_pos = attr.ib()
  end_pos = attr.ib()
  string = attr.ib()

  def get_end_pos(self):
    return self.start_pos[0], self.start_pos[1] + len(self.string)

  def sort_pos(self, lines):
    return Change.relative_pos(self.end_pos, lines)


@attr.s
class Insert(Change):
  start_pos = attr.ib()
  string = attr.ib()

  def get_end_pos(self):
    return self.start_pos[0], self.start_pos[1] + len(self.string)

  def sort_pos(self, lines):
    return self.start_pos


@attr.s
class Delete(Change):
  start_pos = attr.ib()
  end_pos = attr.ib()

  def get_end_pos(self):
    return self.end_pos

  def sort_pos(self, lines):
    return Change.relative_pos(self.end_pos, lines)


def _validate_changes(lines, replacements, inserts, deletes):
  iter_inserts = iter(sorted(iter(inserts), key=lambda i: i.start_pos))
  iter_replace_or_delete = iter(sorted(chain(iter(replacements), iter(deletes)), key=lambda i: i.start_pos))
  iter_replacements = iter(sorted(iter(replacements), key=lambda i: i.start_pos))
  iter_deletes = iter(sorted(iter(deletes), key=lambda i: i.start_pos))

  # TODO: Cleanup - these two branches are nearly identical.
  # First, check that no replace is occurring with a delete. Then, check the same for insertions in
  # replacements and deletes.
  try:
    replace = next(iter_replacements)
    delete = next(iter_deletes)
    while True:
      if replace.end_pos <= delete.start_pos:
        replace = next(iter_replacements)
      else:
        end_pos = delete.end_pos if delete.end_pos[1] >= 0 else (delete.end_pos[0],
                                                                 len(lines[delete.end_pos[0]]) +
                                                                 delete.end_pos[1])
        if replace.start_pos > end_pos:
          delete = next(iter_deletes)
        else:
          assert False, "replaceing into a delete"
  except StopIteration:
    pass
  try:
    insert = next(iter_inserts)
    replace_or_delete = next(iter_replace_or_delete)
    while True:
      if insert.start_pos <= replace_or_delete.start_pos:
        insert = next(iter_inserts)
      else:
        end_pos = replace_or_delete.end_pos if replace_or_delete.end_pos[1] >= 0 else (
            replace_or_delete.end_pos[0],
            len(lines[replace_or_delete.end_pos[0]]) + replace_or_delete.end_pos[1])
        if insert.start_pos > end_pos:
          replace_or_delete = next(iter_replace_or_delete)
        else:
          assert False, "Inserting into a delete or replace"
  except StopIteration:
    pass


def apply_changes_to_string(string, replacements, inserts, deletes):
  if not inserts and not deletes:
    return string

  lines = [f'{l}\n' for l in string.splitlines()]
  replacements = sorted(replacements, key=lambda i: i.sort_pos(lines))
  inserts = sorted(inserts, key=lambda i: i.sort_pos(lines))
  deletes = sorted(deletes, key=lambda r: r.sort_pos(lines))

  # Sanity checking step. Ensure we didn't create a situation we can't handle.
  _validate_changes(lines, replacements, inserts, deletes)

  combined = sorted(chain(replacements, deletes, inserts),
                    key=lambda x: (-x.sort_pos(lines)[0], -x.sort_pos(lines)[1]))
  out = []
  last_start_pos = (len(lines) - 1, -1)

  def add_range(start_pos, end_pos, start_inclusive=False):
    if start_pos == end_pos or (end_pos < start_pos):
      return

    if start_pos[0] != end_pos[0]:
      out.append(lines[end_pos[0]][:end_pos[1]])

    for i in range(start_pos[0] + 1, end_pos[0])[::-1]:
      out.append(lines[i])
    if start_pos[1] != -1:
      out.append(lines[start_pos[0]][start_pos[1] + (0 if start_inclusive else 1):])

  for change in combined:
    if isinstance(change, Delete) or isinstance(change, Replace):
      start_pos = change.end_pos if change.end_pos[1] >= 0 else (change.end_pos[0],
                                                                 (len(lines[change.end_pos[0]]) +
                                                                  change.end_pos[1]))
      start_pos= start_pos[0], start_pos[1] - 1 # Want to include end_pos.
    else:  # Insert.
      if change.start_pos[1] == 0:
        start_pos = (change.start_pos[0] - 1), (len(lines[change.start_pos[0] - 1]) - 1)
      else:
        start_pos = change.start_pos[0], change.start_pos[1] - 1
    add_range(start_pos, last_start_pos)
    if isinstance(change, Replace):
      out.append(change.string)
    last_start_pos = change.start_pos
    if isinstance(change, Insert):
      out.append(change.string)
  add_range((0, 0), last_start_pos, start_inclusive=True)

  # The above approach strips the new-line at the end with splitlines - readd.
  return f'{"".join(reversed(out))}\n'