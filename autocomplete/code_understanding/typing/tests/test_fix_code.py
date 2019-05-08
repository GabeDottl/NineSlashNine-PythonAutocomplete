import os

from autocomplete.code_understanding.typing import api, symbol_index
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (FromImportCfgNode, ImportCfgNode)
from autocomplete.code_understanding.typing.project_analysis import fix_code

HOME = os.getenv('HOME')


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
c = AClass()
'''
  index = symbol_index.SymbolIndex()
  index.add_file(f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing/examples/exports.py')
  graph = api.graph_from_source(source)
  fixes = fix_code.generate_missing_symbol_fixes(graph, index)
  assert len(fixes) == 3


if __name__ == "__main__":
  test_strip_imports()
  test_add_imports()
