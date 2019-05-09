import os
from glob import glob

from autocomplete.code_understanding.typing import api, symbol_index
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (FromImportCfgNode, ImportCfgNode)
from autocomplete.code_understanding.typing.project_analysis import (find_missing_symbols, fix_code)
from autocomplete.nsn_logging import info

CODE = os.getenv('CODE')


def test_strip_imports():
  source = '''
import foo
from functools import wraps

a = wraps  # TODO: decorator.
foo.bar()
'''
  graph = api.graph_from_source(source)
  assert len(list(graph.get_descendents_of_types((ImportCfgNode, FromImportCfgNode)))) == 2
  assert len(graph.get_non_local_symbols()) == 0
  stripped_graph = graph.strip_descendents_of_types((ImportCfgNode, FromImportCfgNode), recursive=False)
  assert len(stripped_graph.get_non_local_symbols()) == 2


def test_add_imports():
  source = '''
b = a_int
a_func()
c = AClass()'''
  index = symbol_index.SymbolIndex()
  index.add_file(
      f'{CODE}/autocomplete/autocomplete/code_understanding/typing/examples/index_test_package/exports.py')
  new_source = fix_code.fix_missing_symbols_in_source(
      source, index,
      f'{CODE}/autocomplete/autocomplete/code_understanding/typing/examples/index_test_package')
  graph = api.graph_from_source(new_source)
  print(new_source)
  assert len(list(graph.get_descendents_of_types(FromImportCfgNode))) == 3
  assert len(graph.get_non_local_symbols()) == 0


def test_fix_imports_typing_match_actual():
  index = symbol_index.SymbolIndex.load(f'{CODE}/autocomplete/index.msg')
  typing_dir = os.path.join(os.path.dirname(__file__), '..')
  filenames = glob(os.path.join(typing_dir, '*.py'), recursive=True)
  for filename in filter(lambda f: 'grammar.py' not in f and 'examples' not in f, filenames):
    info(f'filename: {filename}')
    with open(filename) as f:
      source = ''.join(f.readlines())
    graph = api.graph_from_source(source)
    missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(graph)
    assert not missing_symbols
    existing_imports = list(graph.get_descendents_of_types((ImportCfgNode, FromImportCfgNode)))
    stripped_graph = graph.strip_descendents_of_types((ImportCfgNode, FromImportCfgNode), recursive=False)
    missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(stripped_graph)
    directory = os.path.abspath(os.path.dirname(filename))
    fixes = fix_code.generate_missing_symbol_fixes(missing_symbols, index, directory)

    # Validate fixes
    for fix in fixes:
      for existing_import in existing_imports:
        if fix_code.does_import_match_cfg_node(fix, existing_import, directory):
          break
      else:
        assert False

    # name = os.path.splitext(os.path.basename(filename))[0]
    assert len(fixes) == len(missing_symbols)
    # assert not missing_symbols


if __name__ == "__main__":
  test_fix_imports_typing_match_actual()
  test_strip_imports()
  test_add_imports()
