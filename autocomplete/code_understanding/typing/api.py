import argparse
from autocomplete.code_understanding.typing import frame

import parso
from autocomplete.code_understanding.typing import control_flow_graph
from autocomplete.code_understanding.typing.control_flow_graph_nodes import CfgNode
from autocomplete.code_understanding.typing.collector import Collector
from autocomplete.nsn_logging import info


def graph_from_source(source):
  basic_node = parso.parse(source)
  builder = control_flow_graph.ControlFlowGraphBuilder()
  return builder.create_cfg_node(basic_node)


def frame_from_source(source):
  return control_flow_graph.run_graph(graph_from_source(source))


def collector_from_source(source):
  collector = Collector()
  CfgNode.collector = collector
  graph = graph_from_source(source)
  a_frame = frame.Frame()
  graph.process(a_frame)
  info(f'len(collector.functions): {len(collector.functions)}')
  for func in collector.functions:
    info(f'Calling {func.name}')
    func.call([], {}, a_frame)

  CfgNode.collector = None  # Cleanup.
  return collector


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('source')
  args, _ = parser.parse_known_args()
  with open(args.source) as f:
    source = ''.join(f.readlines())
    print(collector_from_source(source))

    # info(frame_)````
