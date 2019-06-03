import attr
from . import (ast_control_flow_graph_builder, errors, parso_control_flow_graph_builder)
from .control_flow_graph_nodes import (GroupCfgNode, NoOpCfgNode, ModuleCfgNode)


def condense_graph(graph):
  if not isinstance(graph, GroupCfgNode):
    return graph

  children = [condense_graph(child) for child in graph.children]
  children = list(filter(lambda x: not isinstance(x, NoOpCfgNode), children))
  if isinstance(graph, ModuleCfgNode):
    if len(children) == 1 and isinstance(children[0], GroupCfgNode):
      return ModuleCfgNode(children[0].children, parse_node=graph.parse_node)
    return ModuleCfgNode(children, parse_node=graph.parse_node)
  if not children:
    return NoOpCfgNode(graph.parse_node)
  elif len(children) == 1:
    return children[0]
  return GroupCfgNode(children, parse_node=graph.parse_node)


@attr.s
class ControlFlowGraphBuilder:
  module_loader = attr.ib()
  parso_default = attr.ib(False)

  def graph_from_source(self, source, source_filename, module):
    # Note: We condense everything in here so that global imports are at the second-level of the
    # graph (i.e. children of the ModuleCfgNode).
    if self.parso_default:
      builder = parso_control_flow_graph_builder.ParsoControlFlowGraphBuilder(self.module_loader, module)
      return condense_graph(builder.graph_from_source(source, source_filename))
    # Try AST-based builder first because it's waaay faster.
    try:
      builder = ast_control_flow_graph_builder.AstControlFlowGraphBuilder(self.module_loader, module)
      return condense_graph(builder.graph_from_source(source, source_filename))
    except errors.AstUnableToParse:
      builder = parso_control_flow_graph_builder.ParsoControlFlowGraphBuilder(self.module_loader, module)
      return condense_graph(builder.graph_from_source(source, source_filename))