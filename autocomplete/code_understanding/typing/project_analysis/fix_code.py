from typing import List, Union

import attr
from autocomplete.code_understanding.typing import api, symbol_index
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (CfgNode)
from autocomplete.code_understanding.typing.project_analysis import (find_missing_symbols)


def fix_missing_symbols_in_file(filename):
  with open(filename) as f:
    source = ''.join(f.readlines())
  new_code = fix_missing_symbols_in_source(source)
  # TODO


def fix_missing_symbols_in_source(source) -> str:
  graph = api.graph_from_source(source)


class Rename:
  ...


@attr.s
class Import:
  module_name = attr.ib()
  module_filename = attr.ib()
  value = attr.ib()


def generate_missing_symbol_fixes(graph: CfgNode,
                                  index: symbol_index.SymbolIndex) -> List[Union[Rename, Import]]:
  missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(graph)
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
