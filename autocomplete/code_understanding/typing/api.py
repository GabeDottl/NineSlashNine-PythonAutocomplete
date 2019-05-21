
from . import collector, control_flow_graph, module_loader
from .control_flow_graph_nodes import CfgNode
from .language_objects import Function, create_main_module
from .pobjects import AugmentedObject, FuzzyBoolean


def graph_from_source(source: str, source_dir: str, module=None, parso_default=False) -> CfgNode:
  if not module:
    module = create_main_module(module_loader)
  builder = control_flow_graph.ControlFlowGraphBuilder(module_loader, parso_default=parso_default)
  return builder.graph_from_source(source, source_dir, module)
