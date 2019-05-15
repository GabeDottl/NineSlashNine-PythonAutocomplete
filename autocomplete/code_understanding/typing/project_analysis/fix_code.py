import os
import sys
from functools import partial
from itertools import chain
from typing import Dict, List, Union
from collections import defaultdict

import attr
from autocomplete.code_understanding.typing import (api, module_loader, symbol_context, symbol_index,
                                                    refactor)
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (CfgNode, FromImportCfgNode,
                                                                             ImportCfgNode)
from autocomplete.code_understanding.typing.project_analysis import (find_missing_symbols, fix_code)
from autocomplete.nsn_logging import warning, info
from isort import SortImports


def fix_missing_symbols_in_file(filename, index, write=True, remove_extra_imports=False):
  with open(filename) as f:
    source = ''.join(f.readlines())
  new_code = fix_missing_symbols_in_source(source, index, os.path.dirname(filename))
  if write:
    with open(filename, 'w') as f:
      f.writelines(new_code)
  return new_code


def fix_missing_symbols_in_source(source, index, source_dir, remove_extra_imports=False) -> str:
  graph = api.graph_from_source(source, parso_default=True)
  existing_imports = list(graph.get_descendents_of_types((ImportCfgNode, FromImportCfgNode)))
  # TODO: remove_extra_imports=False
  missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(graph)
  info(f'missing_symbols: {list(missing_symbols.keys())}')
  fixes = generate_missing_symbol_fixes(missing_symbols, index, source_dir)
  changes = defaultdict(list)
  remaining_fixes = []
  for fix in fixes:
    module_name, value = fix.get_module_name_and_value(source_dir)
    if not value:
      remaining_fixes.append(fix)
      continue
    for node in filter(lambda x: isinstance(x, FromImportCfgNode), existing_imports):
      if node.module_path == module_name:
        changes[module_name].append((value, None, node))
        break
    else:
      remaining_fixes.append(fix)

  # Update existing imports.
  new_source = refactor.apply_import_changes(source, changes.values())

  # Apply any remaining fixes.
  return refactor.insert_imports(new_source, source_dir, remaining_fixes)


def apply_fixes_to_source(source, source_dir, fixes):
  # TODO: Intelligently inject these w/o sorting - e.g. infer style.
  code_insertion = ''.join([fix.to_code(source_dir) for fix in fixes])
  new_source = code_insertion + source
  return SortImports(file_contents=new_source).output


def _relative_from_path(filename, directory):
  if filename[-(len('__init__.py')):] == '__init__.py':
    filename = filename[:-len('__init__.py') - 1]
    return filename[len(directory) + 1:].replace(os.sep, '.')
  elif filename[-(len('__init__.pyi')):] == '__init__.pyi':
    filename = filename[:-len('__init__.pyi') - 1]
    return filename[len(directory) + 1:].replace(os.sep, '.')
  return os.path.splitext(filename[len(directory) + 1:])[0].replace(os.sep, '.')


def module_name_from_filename(filename, source_dir):
  for path in sorted(sys.path, key=lambda p: -len(p)):
    if path == '.':
      path = source_dir
    if path == filename[:len(path)]:
      return _relative_from_path(filename, path)
  assert False


def does_import_match_cfg_node(import_, cfg_node, directory):
  assert isinstance(cfg_node, (ImportCfgNode, FromImportCfgNode))
  module_name, value = import_.get_module_name_and_value(directory)
  if isinstance(cfg_node, ImportCfgNode):
    if value:
      return False
    module_key, _, _ = module_loader.get_module_info_from_name(cfg_node.module_path, directory)
    if module_key.path != import_.module_filename:
      return False
    return True

  # FromImportCfgNode.
  filename = ''
  for from_import_name, as_name in cfg_node.from_import_name_alias_dict.items():
    filename = module_loader.get_module_info_from_name(f'{cfg_node.module_path}.{from_import_name}',
                                                       directory)[0].path
    # If the from import is importing a module itself, then put it in the module_name
    if not filename:
      filename = module_loader.get_module_info_from_name(cfg_node.module_path, directory)[0].path
    if not filename:
      if module_name != cfg_node.module_path:
        continue
    else:
      if filename != import_.module_filename:
        continue

    if from_import_name == '*':
      return True

    imported_symbol = as_name if as_name else from_import_name
    if not value:
      name = module_name_from_filename(import_.module_filename, directory)
      return imported_symbol == name[name.rfind('.') + 1:]

    if value == imported_symbol:
      return True
  return False


class Rename:
  ...


@attr.s
class Import:
  # DO NOT ACCESS THESE DIRECTLY. Use get_module_name_and_value.
  _module_key = attr.ib()
  as_name = attr.ib()
  # module_filename = attr.ib()
  _value = attr.ib()

  # TODO @instance_memoize
  def get_module_name_and_value(self, source_dir):
    if self._module_key.module_source_type != module_loader.ModuleSourceType.BUILTIN:
      module_name = module_name_from_filename(self._module_key.path, source_dir)
    else:
      module_name = self._module_key.path

    value = self._value
    if not self._value:
      if '.' in module_name:
        i = module_name.rfind('.')
        value = module_name[i + 1:]
        if i > 0:
          module_name = module_name[:i]
        else:
          module_name = '.'

    return module_name, value

  def to_code(self, source_dir):
    module_name, value = self.get_module_name_and_value(source_dir)
    if value:
      return f'from {module_name} import {value}\n'
    return f'import {module_name}\n'


def matches_context(context, symbol_entry):
  # TODO: Refine all of this.
  # If we don't know what the symbol is, assume it matches by default.
  if symbol_entry.symbol_type == symbol_index.SymbolType.AMBIGUOUS or symbol_entry.symbol_type == symbol_index.SymbolType.UNKNOWN:
    return True

  if isinstance(context, symbol_context.MultipleSymbolContext):
    return all(matches_context(c, symbol_entry) for c in context.contexts)

  if isinstance(context, symbol_context.CallSymbolContext):
    # TODO: param check.
    return symbol_entry.symbol_type == symbol_index.SymbolType.FUNCTION or symbol_entry.symbol_type == symbol_index.SymbolType.TYPE

  if isinstance(context, symbol_context.SubscriptSymbolContext):
    return symbol_entry.symbol_type != symbol_index.SymbolType.FUNCTION

  if isinstance(context, symbol_context.AttributeSymbolContext):
    return symbol_entry.symbol_type != symbol_index.SymbolType.FUNCTION

  return True


def symbol_entry_preference_key(symbol_entry):
  return (symbol_entry.import_count, not symbol_entry.imported, symbol_entry.is_module_itself)


def file_distance(symbol_entry, index, directory):
  if symbol_entry.module_type.is_native():
    return -4  # Relatively random default.
  module_filename = index.get_module_filename_from_symbol_entry(symbol_entry)
  a_iter = iter(directory)
  b_iter = iter(module_filename)

  for a, b in zip(a_iter, b_iter):
    if a != b:
      a_iter = chain([a], a_iter)
      b_iter = chain([b], b_iter)
      break

  a_rem = ''.join(a_iter)
  b_rem = ''.join(b_iter)
  return -max(a_rem.count(os.sep), b_rem.count(os.sep))


def relative_symbol_entry_preference_key(symbol_entry, index, directory):
  return tuple(
      list(symbol_entry_preference_key(symbol_entry)) + [file_distance(symbol_entry, index, directory)])


def key_list(l, key_fn):
  for x in l:
    yield x, key_fn(x)


def sort_keyed(l):
  return sorted(l, key=lambda kv: kv[1])


def generate_missing_symbol_fixes(missing_symbols: Dict[str, symbol_context.SymbolContext],
                                  index: symbol_index.SymbolIndex, directory) -> List[Union[Rename, Import]]:

  out = []
  for symbol, context in missing_symbols.items():
    # Prefer symbols which are imported already very often.
    entries = sorted(filter(partial(matches_context, context), index.find_symbol(symbol)),
                     key=symbol_entry_preference_key)
    if not entries:
      warning(f'Could not find import for {symbol}')
      continue
    # TODO: Compare symbol_context w/entry.
    if len(entries) > 1 and symbol_entry_preference_key(entries[-1]) == symbol_entry_preference_key(
        entries[-2]):
      keyed_entries = key_list(entries, lambda x: relative_symbol_entry_preference_key(x, index, directory))
      keyed_entries = sort_keyed(keyed_entries)
      if keyed_entries[-1][1] == keyed_entries[-2][1]:
        warning(
            f'Ambiguous for {symbol} : {keyed_entries[-1][0]} - {index.get_module_str(keyed_entries[-1][0])}\n{keyed_entries[-2][0]} - {index.get_module_str(keyed_entries[-2][0])}'
        )
        continue
      entry = keyed_entries[-1][0]
    else:
      entry = entries[-1]

    module_key = index.get_module_key_from_symbol_entry(entry)

    as_name = None
    if entry.is_module_itself:
      # Example: import pandas
      value = None
      if entry.real_name:  # Should be module_name
        # Example: import pandas as pd
        as_name = symbol
    elif entry.real_name:
      # Example: From a import b as c
      value = entry.real_name
      as_name = symbol
    else:
      # From a import b.
      value = symbol
    out.append(Import(module_key, as_name, value))
    # TODO: Renames.
  return out


def main(index_file, target_file):
  assert os.path.exists(index_file)
  assert os.path.exists(target_file)
  index = symbol_index.SymbolIndex.load(index_file)
  fix_missing_symbols_in_file(target_file, index)


if __name__ == "__main__":
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('index_file')
  parser.add_argument('target_file')
  args = parser.parse_args()
  main(args.index_file, args.target_file)
