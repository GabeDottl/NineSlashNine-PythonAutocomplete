import os
from glob import glob

from .. import api, symbol_index
from ..control_flow_graph_nodes import (FromImportCfgNode, ImportCfgNode)
from ..project_analysis import (find_missing_symbols, fix_code)
from ....nsn_logging import info

CODE = os.getenv('CODE')


def test_strip_imports():
  source = '''
import foo
from functools import wraps

a = wraps  # TODO: decorator.
foo.bar()
'''
  graph = api.graph_from_source(source, os.path.dirname(__file__))
  assert len(list(graph.get_descendents_of_types((ImportCfgNode, FromImportCfgNode)))) == 2
  assert len(graph.get_non_local_symbols()) == 0
  stripped_graph = graph.strip_descendents_of_types((ImportCfgNode, FromImportCfgNode), recursive=False)
  assert len(stripped_graph.get_non_local_symbols()) == 2


def test_add_all_imports():
  source = '''
b = a_int
a_func()
c = AClass()'''
  index = symbol_index.SymbolIndex()
  index.add_file(os.path.join(os.path.dirname(__file__), '..', 'examples', 'index_test_package',
                              'exports.py'))
  new_source, changed = fix_code.fix_missing_symbols_in_source(source, os.path.dirname(__file__), filename=None, index=index)
  graph = api.graph_from_source(new_source, os.path.dirname(__file__))
  print(new_source)
  assert changed
  assert len(list(graph.get_descendents_of_types(FromImportCfgNode))) == 1
  assert len(graph.get_non_local_symbols()) == 0


def test_add_imports_with_existing():
  source = '''
from ..examples.index_test_package.exports import (AClass,
                                                                                        a_int)

c = attr.ib()
b = a_int
a_func()
c = AClass()'''
  # TODO: Windows support for /tmp.
  index = symbol_index.SymbolIndex.build_index_from_package(
      os.path.join(os.path.dirname(__file__), '..', 'examples', 'index_test_package'), '/tmp/tmp.msg')
  new_source, changed = fix_code.fix_missing_symbols_in_source(source, os.path.dirname(__file__), filename=None, index=index)
  graph = api.graph_from_source(new_source, os.path.dirname(__file__))
  print(new_source)
  assert len(list(graph.get_descendents_of_types(FromImportCfgNode))) == 1
  assert len(graph.get_non_local_symbols()) == 0


def test_fix_imports_typing_match_actual():
  from .... import code_understanding
  autocomplete_dir = os.path.join(os.path.dirname(code_understanding.__file__), '..', '..')
  index = symbol_index.SymbolIndex.load(os.path.join(autocomplete_dir, 'index.msg'))
  typing_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
  filenames = glob(os.path.join(typing_dir, '**/*.py'), recursive=True)
  for filename in filter(lambda f: 'grammar.py' not in f and 'examples' not in f, filenames):
    info(f'filename: {filename}')
    with open(filename) as f:
      source = ''.join(f.readlines())
    graph = api.graph_from_source(source, os.path.dirname(filename))
    missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(graph, os.path.dirname(filename))
    assert not missing_symbols
    existing_imports = list(graph.get_descendents_of_types((ImportCfgNode, FromImportCfgNode)))
    stripped_graph = graph.strip_descendents_of_types((ImportCfgNode, FromImportCfgNode), recursive=False)
    missing_symbols = find_missing_symbols.scan_missing_symbols_in_graph(stripped_graph,
                                                                         os.path.dirname(filename))
    directory = os.path.abspath(os.path.dirname(filename))
    fixes, still_missing = fix_code.generate_missing_symbol_fixes(missing_symbols, index, directory)

    # Validate fixes
    for fix in fixes:
      for existing_import in existing_imports:
        if fix_code.does_import_match_cfg_node(fix, existing_import, directory):
          break
      else:
        assert False

    assert not still_missing


if __name__ == "__main__":
  test_add_imports_with_existing()
  test_add_all_imports()
  test_fix_imports_typing_match_actual()
  test_strip_imports()
