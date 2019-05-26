import ast
import _ast

from .. import api

def get_mode(ast_node):
  if isinstance(ast_node, _ast.Module):
    return 'exec'
  else:
    return 'eval'


def test_literal():
  for s in ('1', '1.1', '1j', '"str"', 'b"bytes"', 'None', 'True'):
    graph = api.graph_from_source(s, '<string>')
    ast_graph = graph.to_ast()
    ast_graph = ast.fix_missing_locations(ast_graph)
    code_obj =compile(ast_graph, '<ast>', get_mode(ast_graph), optimize=-1)
    globals_, locals_ = {}, {}
    assert eval(code_obj, globals_, locals_) == eval(s)

if __name__ == "__main__":
  test_literal()