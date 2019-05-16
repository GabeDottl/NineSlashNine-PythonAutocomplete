# from __future__ import annotations
# Each statement is a node, each linear group is a subgraph?
#
# When control flow is hit, a branch is created.
#
# a = 1 # n1
# b = a + 2 # n2
# if True: #n3
#   b = 'asdf' # n4
# else: b = True # n5
# c = 3 # n6
# # n1 -> n2 -> n3
# #                -> n4
# #                     -> n6
# #                -> n5
# #                     -> n6
#
# DFS down tree to node to determine values
# - Memoize where possible + shortcut
import sys
import traceback
from functools import wraps
from typing import List, Tuple

import attr
from . import (ast_control_flow_graph_builder, errors, language_objects, parso_control_flow_graph_builder)
from .control_flow_graph_nodes import (AssignmentStmtCfgNode, CfgNode, ExceptCfgNode, ExpressionCfgNode,
                                       ForCfgNode, FromImportCfgNode, FuncCfgNode, GroupCfgNode, IfCfgNode,
                                       ImportCfgNode, KlassCfgNode, NoOpCfgNode, ReturnCfgNode, TryCfgNode,
                                       WhileCfgNode, WithCfgNode)
from .errors import ParsingError
from .expressions import (AnonymousExpression, Expression, LiteralExpression, UnknownExpression,
                          VariableExpression)
from .frame import Frame
from .pobjects import NONE_POBJECT
from ...nsn_logging import debug, error, info, warning


def condense_graph(graph):
  if not isinstance(graph, GroupCfgNode):
    return graph

  children = [condense_graph(child) for child in graph.children]
  children = list(filter(lambda x: not isinstance(x, NoOpCfgNode), children))
  if not children:
    return NoOpCfgNode(graph.parse_node)
  elif len(children) == 1:
    return children[0]
  return GroupCfgNode(children, parse_node=graph.parse_node)


@attr.s
class ControlFlowGraphBuilder:
  module_loader = attr.ib()
  parso_default = attr.ib(False)

  def graph_from_source(self, source, source_dir, module):
    if self.parso_default:
      builder = parso_control_flow_graph_builder.ParsoControlFlowGraphBuilder(self.module_loader, module)
      return builder.graph_from_source(source, source_dir)
    # Try AST-based builder first because it's waaay faster.
    try:
      builder = ast_control_flow_graph_builder.AstControlFlowGraphBuilder(self.module_loader, module)
      builder.graph_from_source(source, source_dir)
    except errors.AstUnableToParse:
      builder = parso_control_flow_graph_builder.ParsoControlFlowGraphBuilder(self.module_loader, module)
    return builder.graph_from_source(source, source_dir)
