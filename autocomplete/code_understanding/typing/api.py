import argparse

from . import (collector, control_flow_graph, frame, module_loader)
from .control_flow_graph_nodes import (CfgNode)
from .expressions import (UnknownExpression)
from .language_objects import (Function, Klass, create_main_module)
from .pobjects import (AugmentedObject, FuzzyBoolean, UnknownObject)
from ...nsn_logging import debug, info


def graph_from_source(source: str, source_dir: str, module=None, parso_default=False) -> CfgNode:
  if not module:
    module = create_main_module(module_loader)
  builder = control_flow_graph.ControlFlowGraphBuilder(module_loader, parso_default=parso_default)
  return builder.graph_from_source(source, source_dir, module)


def analyze_file(filename):
  module = module_loader.get_module_from_filename(filename, is_package=False, lazy=False)
  with collector.FileContext(filename):
    debug(f'len(collector.functions): {len(collector._functions)}')
    a_frame = frame.Frame(module=module, namespace=module)
    for key, member in module.items():
      _process(member, a_frame)
    return collector._functions  # TODO: ????


def _process(member, a_frame):
  if isinstance(member, AugmentedObject) and member.value_is_a(Klass) == FuzzyBoolean.TRUE:
    instance = member.value().new(a_frame, [], {})
    for _, value in instance.items():
      _process(value, a_frame)
  elif isinstance(member, AugmentedObject) and member.value_is_a(Function) == FuzzyBoolean.TRUE:
    func = member.value()
    debug(f'Calling {func.name}')
    kwargs = {param.name: UnknownObject(param.name) for param in func.parameters}
    func.call(a_frame, [], kwargs)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('filename')
  args, _ = parser.parse_known_args()
  print(analyze_file(args.filename))
