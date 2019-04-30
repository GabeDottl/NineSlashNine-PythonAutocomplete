import argparse

import parso

from autocomplete.code_understanding.typing import (
    collector, control_flow_graph, frame, module_loader)
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (
    CfgNode)
from autocomplete.code_understanding.typing.expressions import (
    UnknownExpression)
from autocomplete.code_understanding.typing.language_objects import (
    Function, Klass, create_main_module)
from autocomplete.code_understanding.typing.pobjects import (
    AugmentedObject, FuzzyBoolean, UnknownObject)
from autocomplete.nsn_logging import debug, info


def graph_from_source(source: str, module=None) -> CfgNode:
  basic_node = parso.parse(source)
  if not module:
    module = create_main_module()
  builder = control_flow_graph.ControlFlowGraphBuilder(module_loader, module)
  return builder.graph_from_parso_node(basic_node)


# def frame_from_source(source: str, filename: str) -> frame.Frame:
#   with collector.FileContext(filename):

#     return control_flow_graph.run_graph(graph_from_source(source))


def analyze_file(filename):
  #   with open(filename) as f:
  #     source = ''.join(f.readlines())
  #     with collector.FileContext(filename):
  #       return collector_from_source(source)

  # def collector_from_source(source: str):
  module = module_loader.get_module_from_filename(
      '', filename, is_package=False, lazy=False)
  # graph = graph_from_source(source)
  # a_frame = frame.Frame()
  # graph.process(a_frame)
  with collector.FileContext(filename):
    debug(f'len(collector.functions): {len(collector._functions)}')
    a_frame = frame.Frame(module=module, namespace=module)
    for key, member in module.items():
      _process(member, a_frame)
    return collector._functions  # TODO: ????


def _process(member, a_frame):
  if isinstance(
      member,
      AugmentedObject) and member.value_is_a(Klass) == FuzzyBoolean.TRUE:
    instance = member.value().new(a_frame, [], {})
    for _, value in instance.items():
      _process(value, a_frame)
  elif isinstance(
      member,
      AugmentedObject) and member.value_is_a(Function) == FuzzyBoolean.TRUE:
    func = member.value()
    debug(f'Calling {func.name}')
    kwargs = {
        param.name: UnknownObject(param.name) for param in func.parameters
    }
    func.call(a_frame, [], kwargs)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('filename')
  args, _ = parser.parse_known_args()
  print(analyze_file(args.filename))
