import argparse
from os import readlink

import parso
from autocomplete.code_understanding.typing import control_flow_graph


def frame_from_source(source):
  basic_node = parso.parse(source)
  builder = control_flow_graph.ControlFlowGraphBuilder()
  graph = builder.create_cfg_node(basic_node)
  return control_flow_graph.run_graph(graph)

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('source')
  args = parser.parse_args()
  with open(args.source) as f:
    source = ''.join(f.readlines())
    frame_ = frame_from_source(source)
    # info(frame_)