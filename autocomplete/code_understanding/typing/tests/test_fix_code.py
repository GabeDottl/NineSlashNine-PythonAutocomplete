from autocomplete.code_understanding.typing import api
from autocomplete.code_understanding.typing.control_flow_graph_nodes import ImportCfgNode, FromImportCfgNode

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

if __name__ == "__main__":
    test_strip_imports()