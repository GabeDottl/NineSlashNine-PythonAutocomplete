import attr
from itertools import chain

import _ast
from typing import Dict, List, Tuple
from collections import defaultdict, OrderedDict
from ...nsn_logging import info
from . import control_flow_graph_nodes, api, expressions


@attr.s
class Change:
  cfg_node = attr.ib()
  additions = attr.ib()
  removals = attr.ib()


def apply_import_changes(source: str, changes: List[Change]) -> str:
  # TODO: Create a little OSS lib for apply multiple operations to a single string creation.
  # ADD, DELETE, REPLACE.
  # Otherwise, we're essentially recreating an arbi
  new_source = source
  # Turn this into a dict so we can delete from it without shifting lines.
  new_source_lines = OrderedDict()
  for i, l in enumerate(source.splitlines()):
    new_source_lines[i] = l
  # TODO: Migrate this to apply_insert_and_removals func & merge with insert_imports.
  for change in changes:
    parso_node = change.cfg_node.parse_node.native_node
    assert not isinstance(parso_node, _ast.AST), "Must create graph w/parso."
    if isinstance(change.cfg_node, control_flow_graph_nodes.ImportCfgNode):
      assert not change.additions
      assert len(change.removals) == 1
      for i in range(parso_node.start_pos[0], parso_node.end_pos[0] + 1):
        del new_source_lines[i - 1]
      continue

    if not change.additions and len(change.removals) == len(change.cfg_node.from_import_name_alias_dict):
      # Removing the entire from_import
      for i in range(parso_node.start_pos[0], parso_node.end_pos[0] + 1):
        del new_source_lines[i - 1]
    else:
      new_from_imports = set(add for add in change.additions)
      removals = set(change.removals)
      for value, as_name in change.cfg_node.from_import_name_alias_dict.items():
        if value not in removals:
          new_from_imports.add((value, as_name))

      start_pos, end_pos = change.cfg_node.parse_node.extras
      if start_pos[0] == end_pos[0]:
        line = new_source_lines[start_pos[0] - 1]
        line = f'{line[:start_pos[1]]}{line[end_pos[1]:]}'
      else:
        line = new_source_lines[start_pos[0] - 1][:start_pos[1]]
        for lineno in range(start_pos[0], end_pos[0]):
          del new_source_lines[lineno]

      insertion_col = start_pos[1]
      if len(new_from_imports) >= 1:
        if len(new_from_imports) > 1:
          new_from_imports = sorted(new_from_imports, key=lambda from_as_name: from_as_name[0])
          insertion = f'({", ".join(import_format(v,a) for v,a in new_from_imports)})'
        else:
          insertion = f'{", ".join(import_format(v,a) for v,a in new_from_imports)}'
        line = f'{line[:insertion_col]}{insertion}{line[insertion_col:]}'
        new_source_lines[start_pos[0] - 1] = line
  return '\n'.join(new_source_lines.values())


def import_format(value, as_name):
  if as_name:
    return f'{value} as {as_name}'
  return value


def insert_imports(source, source_dir, fixes):
  graph = api.graph_from_source(source, source_dir, parso_default=True)
  module_to_value_dict = defaultdict(list)

  module_imports = []
  for fix in fixes:
    module_name, value = fix.get_module_name_and_value(source_dir)
    if not value:
      module_imports.append((module_name, fix.as_name))
    else:
      module_to_value_dict[module_name].append((value, fix.as_name))

  inserts = []
  if module_imports:
    import_nodes = list(graph.get_descendents_of_types(control_flow_graph_nodes.ImportCfgNode))

    if not import_nodes:
      first_node = graph.children[0]
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
  return apply_inserts_and_removals_to_string(source, inserts, [])


@attr.s
class Insert:
  start_pos = attr.ib()
  string = attr.ib()

  def get_end_pos(self):
    return self.start_pos[0], self.start_pos[1] + len(self.string)


@attr.s
class Remove:
  start_pos = attr.ib()
  end_pos = attr.ib()

  def get_end_pos(self):
    return self.end_pos


def _validate_inserts_removals(lines, inserts, removals):
  iter_inserts = iter(inserts)
  iter_removals = iter(removals)
  try:
    insert = next(iter_inserts)
    remove = next(iter_removals)
    while True:
      if insert.start_pos <= remove.start_pos:
        insert = next(iter_inserts)
      else:
        end_pos = remove.end_pos if remove.end_pos[1] >= 0 else remove.end_pos[0], len(
            lines[remove.end_pos[0]]) + remove.end_pos[1]
        if insert.start_pos > end_pos:
          remove = next(iter_removals)
        else:
          assert False, "Inserting into a removal"
  except StopIteration:
    pass


def apply_inserts_and_removals_to_string(string, inserts, removals):
  lines = [f'{l}\n' for l in string.splitlines()]
  inserts = sorted(inserts, key=lambda i: i.start_pos)
  removals = sorted(removals, key=lambda r: r.start_pos)

  # Sanity checking step. Ensure we didn't create a situation we can't handle.
  _validate_inserts_removals(lines, inserts, removals)

  combined = sorted(chain(inserts, removals), key=lambda x: (-x.start_pos[0], -x.start_pos[1]))
  out = []
  last_start_pos = (len(lines) - 1, -1)

  def add_range(start_pos, end_pos, start_inclusive=False):
    if start_pos == end_pos:
      return

    if start_pos[0] != end_pos[0]:
      out.append(lines[end_pos[0]][:end_pos[1]])
      # if end_pos[0] != 0:
      #   out.append('\n')
    for i in range(start_pos[0] + 1, end_pos[0])[::-1]:
      out.append(f'{lines[i]}')
    if start_pos[1] != -1:
      out.append(lines[start_pos[0]][start_pos[1] + (0 if start_inclusive else 1):])

  for change in combined:
    if isinstance(change, Remove):
      start_pos = remove.end_pos if remove.end_pos[1] >= 0 else remove.end_pos[0], len(
          lines[remove.end_pos[0]]) + remove.end_pos[1]
    else:
      if change.start_pos[1] == 0:
        start_pos = change.start_pos[0] - 1, len(lines[change.start_pos[0] - 1]) - 1
      else:
        start_pos = change.start_pos[0], change.start_pos[1] - 1
    add_range(start_pos, last_start_pos)
    last_start_pos = change.start_pos
    if isinstance(change, Insert):
      out.append(change.string)
  add_range((0, 0), last_start_pos, start_inclusive=True)

  return ''.join(reversed(out))
