import os

from autocomplete.code_understanding.typing import collector
from autocomplete.code_understanding.typing.api import graph_from_source
from autocomplete.code_understanding.typing.project_analysis import find_missing_symbols
from autocomplete.code_understanding.typing import control_flow_graph


def test_missing_symbols():
  typing_dir = os.path.join(os.path.dirname(__file__), '..')
  unresolved_imports_filename = os.path.join(typing_dir, 'examples',
                                             'unresolved_symbols.py')
  missing_symbols = find_missing_symbols.scan_missing_symbols(
      unresolved_imports_filename, include_context=False)
  print('Used symbols:',
        collector._referenced_symbols[unresolved_imports_filename])
  # Should be missing unresolved 1 - 4.
  assert len(missing_symbols) == 5, missing_symbols
  for i in range(1, 6):
    assert f'unresolved{i}' in missing_symbols

def test_cfg_symbol_visibility():
  source = '''
  a = 1
  class X:
    b = 2
    def foo():
      c = 3
      with open("a") as f:
        d = f
      while True:
        e = 4
      for i in range(10):
        g = 5
      try:
        h = 6
      except:
        j = 7
      def foo2():
        k = 8
  '''
  graph = graph_from_source(source)
  graph = control_flow_graph.condense_graph(graph)
  _assert_expected_iterable(graph.get_defined_and_exported_symbols(), ['a', 'X'])
  

def _assert_expected_iterable(actual, expected):
  actual = set(actual)
  expected = set(expected)
  difference = actual.difference(expected)
  assert not difference, difference  # Should be empty set.
      

if __name__ == "__main__":
  # test_missing_symbols()
  test_cfg_symbol_visibility()
