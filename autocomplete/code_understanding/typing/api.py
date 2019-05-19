import argparse

from . import collector, control_flow_graph, frame, module_loader
from ...nsn_logging import debug
from .control_flow_graph_nodes import CfgNode
from .language_objects import Function, Klass, create_main_module
from .pobjects import AugmentedObject, FuzzyBoolean, UnknownObject


def graph_from_source(source: str, source_dir: str, module=None, parso_default=False) -> CfgNode:
  if not module:
    module = create_main_module(module_loader)
  builder = control_flow_graph.ControlFlowGraphBuilder(module_loader, parso_default=parso_default)
  return builder.graph_from_source(source, source_dir, module)
