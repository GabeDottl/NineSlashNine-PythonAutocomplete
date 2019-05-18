import os
from glob import glob

from .. import collector, control_flow_graph, module_loader
from ....nsn_logging import info
from ..api import graph_from_source
from ..control_flow_graph_nodes import FuncCfgNode
from ..project_analysis import find_missing_symbols
from ..utils import assert_expected_iterable


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
  graph = graph_from_source(source, os.path.dirname(__file__))
  graph = control_flow_graph.condense_graph(graph)
  assert_expected_iterable(graph.get_defined_and_exported_symbols(), ['a', 'X'])
  klass_node = graph[1]
  assert_expected_iterable(klass_node.get_defined_and_exported_symbols(), ['X'])
  assert_expected_iterable(klass_node.suite.get_defined_and_exported_symbols(), ['b', 'foo'])
  func_node = klass_node.suite[1]
  assert isinstance(func_node, FuncCfgNode)
  assert_expected_iterable(func_node.get_defined_and_exported_symbols(), ['foo'])
  assert_expected_iterable(func_node.suite.get_defined_and_exported_symbols(),
                           ['c', 'f', 'd', 'e', 'g', 'i', 'h', 'j', 'k', 'foo2'])


def test_closure_scope():
  source = '''
  def foo():
    b = a  # global
    b = undefined
    q = 1
    w = 2
    def foo2():
      c = 3
      def foo3():
        print((a,b,c))
      class X:
        a = w
        def foo4(self):
          return c, q

  a = 1
  '''
  graph = graph_from_source(source, os.path.dirname(__file__))
  graph = control_flow_graph.condense_graph(graph)
  foo_func_node = graph[0]
  assert isinstance(foo_func_node, FuncCfgNode)
  assert not foo_func_node.closure()  # Should be empty.
  foo2_func_node = foo_func_node.suite[-1]
  assert isinstance(foo2_func_node, FuncCfgNode)
  assert_expected_iterable(foo2_func_node.closure(), ['b', 'w', 'q'])
  foo3_func_node = foo2_func_node.suite[1]
  assert isinstance(foo3_func_node, FuncCfgNode)
  assert_expected_iterable(foo3_func_node.closure(), ['b', 'c'])
  x_klass_node = foo2_func_node.suite[-1]
  foo4_func_node = x_klass_node.suite[-1]
  assert_expected_iterable(foo4_func_node.closure(), ['c', 'q'])


def test_closure_values():
  source = '''
  def foo(a):
    def foo2():
      return a
    return foo2

  def foo3(a):
    def foo4():
      def foo5():
        return a
      return foo5
    return foo4

  def foo6(a):
    return foo3(3)()()
  a = foo6(9)
  c = foo(1)
  d = foo(2)
  c = c()
  d = d()

  '''
  module = module_loader.load_module_from_source(source)
  assert module['a'].value() == 3
  assert module['c'].value() == 1
  assert module['d'].value() == 2


def test_missing_symbols():
  typing_dir = os.path.join(os.path.dirname(__file__), '..')
  unresolved_imports_filename = os.path.abspath(os.path.join(typing_dir, 'examples', 'unresolved_symbols.py'))

  missing_symbols = find_missing_symbols.scan_missing_symbols_in_file(unresolved_imports_filename)
  print('Used symbols:', collector._referenced_symbols[unresolved_imports_filename])
  # Should be missing unresolved 1 - 4.
  assert len(missing_symbols) == 5, missing_symbols
  for i in range(1, 6):
    assert f'unresolved{i}' in missing_symbols


def test_no_missing_symbols_in_typing_package():
  typing_dir = os.path.join(os.path.dirname(__file__), '..')
  filenames = glob(os.path.join(typing_dir, '*.py'), recursive=True)
  for filename in filter(lambda f: 'grammar.py' not in f, filenames):
    info(f'filename: {filename}')
    # name = os.path.splitext(os.path.basename(filename))[0]
    missing_symbols = find_missing_symbols.scan_missing_symbols_in_file(filename)
    assert not missing_symbols


def test_module_exports():
  HOME = os.getenv('HOME')
  with open(f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing/control_flow_graph.py') as f:
    source = ''.join(f.readlines())
  graph = graph_from_source(source, os.path.dirname(__file__))
  exports = graph.get_defined_and_exported_symbols()
  assert len(exports) >= 40


if __name__ == "__main__":
  test_module_exports()
  test_missing_symbols()
  test_closure_values()
  test_cfg_symbol_visibility()
  test_closure_scope()
  test_no_missing_symbols_in_typing_package()
