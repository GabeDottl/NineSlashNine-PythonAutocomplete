import os

from autocomplete.code_understanding.typing import (collector,
                                                    control_flow_graph)
from autocomplete.code_understanding.typing.api import graph_from_source
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (
    FuncCfgNode)
from autocomplete.code_understanding.typing.project_analysis import (
    find_missing_symbols)


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
      except Exception as exc:
        j = 7
      def foo2():
        k = 8
  '''
  graph = graph_from_source(source)
  graph = control_flow_graph.condense_graph(graph)
  _assert_expected_iterable(graph.get_defined_and_exported_symbols(),
                            ['a', 'X'])
  klass_node = graph[1]
  _assert_expected_iterable(klass_node.get_defined_and_exported_symbols(),
                            ['X'])
  _assert_expected_iterable(klass_node.suite.get_defined_and_exported_symbols(),
                            ['b', 'foo'])
  func_node = klass_node.suite[2]
  assert isinstance(func_node, FuncCfgNode)
  _assert_expected_iterable(func_node.get_defined_and_exported_symbols(),
                            ['foo'])
  _assert_expected_iterable(
      func_node.suite.get_defined_and_exported_symbols(),
      ['c', 'f', 'd', 'e', 'g', 'i', 'h', 'j', 'k', 'foo2'])


def test_closure():
  source = '''
  def foo():
    b = a
    def foo2():
      c = 3
      def foo3():
        print((a,b,c))
      return foo3
    return foo2
  a = 1
  '''
  graph = graph_from_source(source)
  graph = control_flow_graph.condense_graph(graph)
  foo_func_node = graph[0]
  assert isinstance(foo_func_node, FuncCfgNode)
  assert not foo_func_node.closure()  # Should be empty.
  foo2_func_node = foo_func_node.suite[2]
  assert isinstance(foo2_func_node, FuncCfgNode)
  _assert_expected_iterable(foo2_func_node.closure(), ['b'])
  foo3_func_node = foo2_func_node.suite[2]
  assert isinstance(foo3_func_node, FuncCfgNode)
  _assert_expected_iterable(foo3_func_node.closure(), ['b', 'c'])


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


def _assert_expected_iterable(actual, expected):
  actual = set(actual)
  expected = set(expected)
  difference = actual.difference(expected)
  assert not difference, difference  # Should be empty set.


if __name__ == "__main__":
  test_cfg_symbol_visibility()
  test_closure()
  test_missing_symbols()
