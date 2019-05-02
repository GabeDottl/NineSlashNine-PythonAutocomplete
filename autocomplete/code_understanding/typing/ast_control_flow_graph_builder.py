import ast
import attr


@attr.s
class ParsoControlFlowGraphBuilder:
  module_loader = attr.ib()
  _module: 'Module' = attr.ib()
  root: GroupCfgNode = attr.ib(factory=GroupCfgNode)
  _current_containing_func = None

  def graph_from_source(self, source):
    ast_node = parso.parse(source)
    self.root.children.append(self._create_cfg_node(parse_node))
    return self.root
