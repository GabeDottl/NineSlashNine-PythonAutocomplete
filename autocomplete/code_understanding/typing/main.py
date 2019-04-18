import parso

from autocomplete.code_understanding.typing import control_flow_graph, module_loader

if __name__ == '__main__':
  with open(
      '/Users/gabe/code/autocomplete/autocomplete/code_understanding/typing/examples/basic.py'
  ) as f:
    basic_source = ''.join(f.readlines())
    basic_node = parso.parse(basic_source)
    builder = control_flow_graph.ControlFlowGraphBuilder(module_loader)
    graph = builder.create_cfg_node(basic_node)
    a_frame = control_flow_graph.run_graph(graph)
