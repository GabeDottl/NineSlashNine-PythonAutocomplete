import os
import sys
from typing import Dict, List, Union

import attr
from autocomplete.code_understanding.typing import (api, symbol_context, symbol_index)
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (CfgNode)
from autocomplete.code_understanding.typing.project_analysis import (find_missing_symbols, fix_code)
from isort import SortImports


def fix_missing_symbols_in_file(filename, index, write=True):
  with open(filename) as f:
    source = ''.join(f.readlines())
  new_code = fix_missing_symbols_in_source(source, index, os.path.dirname())
  if write:
    with open(filename, 'w') as f:
      f.writelines(new_code)
  return new_code


def fix_missing_symbols_in_source(source, index, source_dir=None) -> str:
  graph = api.graph_from_source(source)
  missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(graph)
  fixes = generate_missing_symbol_fixes(missing_symbols, index)
  return apply_fixes_to_source(source, source_dir, fixes)


def apply_fixes_to_source(source, source_dir, fixes):
  code_insertion = ''.join([fix.to_code(source_dir) for fix in fixes])
  new_source = code_insertion + source
  return SortImports(file_contents=new_source).output


class Rename:
  ...


def _relative_from_path(filename, directory):
  return os.path.splitext(filename[len(directory) + 1:])[0].replace(os.sep, '.')


def module_name_from_filename(filename, source_dir):
  for path in sorted(sys.path, key=lambda p: -len(p)):
    if path == '.':
      path = source_dir
    if path == filename[:len(path)]:
      return _relative_from_path(filename, path)
  assert False


@attr.s
class Import:
  module_name = attr.ib()
  module_filename = attr.ib()
  value = attr.ib()

  def __attrs_post_init__(self):
    assert not (self.module_filename and self.module_name)

  def to_code(self, curr_dir):
    if self.module_filename:
      assert self.module_name is None
      self.module_name = module_name_from_filename(self.module_filename, curr_dir)

    if not self.value:
      if '.' in self.module_name:
        i = self.module_name.rfind('.')
        self.value = self.module_name[i + 1:]
        if i > 0:
          self.module_name = self.module_name[:i]
        else:
          self.module_name = '.'

    if self.value:
      return f'from {self.module_name} import {self.value}\n'
    return f'import {self.module_name}\n'


def generate_missing_symbol_fixes(missing_symbols: Dict[str, symbol_context.SymbolContext],
                                  index: symbol_index.SymbolIndex) -> List[Union[Rename, Import]]:

  out = []
  for symbol, symbol_context in missing_symbols.items():
    entries = index.find_symbol(symbol)
    assert len(entries) == 1
    # TODO: Compare symbol_context w/entry.
    entry = entries[0]
    module_name = index.get_native_module_name_from_symbol_entry(
        entry) if entry.is_from_native_module() else None
    module_filename = index.get_module_filename_from_symbol_entry(
        entry) if not entry.is_from_native_module() else None
    out.append(Import(module_name, module_filename, symbol if not entry.is_module_itself else None))
    # TODO: Renames.
  return out
