import argparse

import parso
from autocomplete.code_understanding.typing import (
    collector, control_flow_graph, frame, module_loader)
from autocomplete.code_understanding.typing.collector import Collector
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (
    CfgNode, FunctionImpl, Klass)
from autocomplete.code_understanding.typing.expressions import (
    UnknownExpression)
from autocomplete.code_understanding.typing.pobjects import (FuzzyBoolean,
                                                             UnknownObject)
from autocomplete.nsn_logging import debug


def graph_from_source(source: str):
  basic_node = parso.parse(source)
  builder = control_flow_graph.ControlFlowGraphBuilder(module_loader)
  return builder.create_cfg_node(basic_node)


def frame_from_source(source: str, filename: str) -> frame.Frame:
  with collector.FileContext(filename):
    return control_flow_graph.run_graph(graph_from_source(source))


def analyze_file(filename):
  with open(filename) as f:
    source = ''.join(f.readlines())
    with collector.FileContext(filename):
      return collector_from_source(source)


def collector_from_source(source: str):
  collector = Collector()  # TODO: Drop
  CfgNode.collector = collector
  graph = graph_from_source(source)
  a_frame = frame.Frame()
  graph.process(a_frame)
  debug(f'len(collector.functions): {len(collector.functions)}')
  for key, member in a_frame._locals.items():
    _process(member, a_frame)
  CfgNode.collector = None  # Cleanup.
  return collector


def _process(member, a_frame):
  if member.value_is_a(Klass) == FuzzyBoolean.TRUE:
    instance = member.value().new([], {}, a_frame)
    for _, value in instance.items():
      _process(value, a_frame)
  elif member.value_is_a(FunctionImpl) == FuzzyBoolean.TRUE:
    func = member.value()
    debug(f'Calling {func.name}')
    kwargs = {param.name: UnknownExpression('') for param in func.parameters}
    func.call([], kwargs, a_frame)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('source')
  args, _ = parser.parse_known_args()
  print(analyze_file(filename))
