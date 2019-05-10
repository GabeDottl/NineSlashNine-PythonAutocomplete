import _ast
from typing import Dict, List, Tuple
from collections import defaultdict


def apply_import_changes(source:str, add_remove_node_tuple_lists: List[List[Tuple[str,str,'CfgNode']]]) -> str:
  # TODO: Create a little OSS lib for apply multiple operations to a single string creation.
  # ADD, DELETE, REPLACE.
  # Otherwise, we're essentially recreating an arbi
  new_source = source
  new_source_lines = source.splitlines()
  for add_remove_node_tuples in add_remove_node_tuple_lists:
    from_import_cfg_node = add_remove_node_tuples[0][-1]
    parso_node = from_import_cfg_node.parse_node.native_node
    assert not isinstance(parso_node, _ast.AST), "Must create graph w/parso."
    insertion_point = list(sorted(from_import_cfg_node.parse_node.extras.values()))[0][0]
    for add, remove, _ in add_remove_node_tuples:
      assert not remove
      # start, end = from_import_cfg_node.parse_node.extras[remove]
      # TODO: Handle multiple insertions more cleanly...
      if add:
        line = new_source_lines[insertion_point[0] - 1]
        new_source_lines[insertion_point[0] - 1] = f'{line[:insertion_point[1]]}{add}, {line[insertion_point[1]:]}'
  return '\n'.join(new_source_lines)

def insert_imports(source, source_dir, fixes):
  module_to_value_dict = defaultdict(list)
  module_imports = []
  for fix in fixes:
    module_name, value = fix.get_module_name_and_value(source_dir)
    if not value:
      module_imports.append(module_name)
    else:
      module_to_value_dict[module_name].append(value)
  
  out = []
  for module_name, values in module_to_value_dict.items():
    if len(values) > 1:
      out.append(f'from {module_name} import ({",".join(values)})\n')
    else:
      out.append(f'from {module_name} import {values[0]}\n')
  for module in module_imports:
    out.append(f'import {module}\n')

  code_insertion = ''.join(out)
  return code_insertion + source
