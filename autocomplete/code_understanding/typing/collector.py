from prettytable import PrettyTable
from collections import defaultdict

import attr
from functools import partial

from autocomplete.code_understanding.typing.control_flow_graph_nodes import (FromImportCfgNode,
                                                                             ImportCfgNode)
from autocomplete.code_understanding.typing.language_objects import Module


@attr.s #(frozen=True)
class ModuleMember:
  module: str = attr.ib(validator=[attr.validators.instance_of(str)])
  member: str = attr.ib(validator=[attr.validators.instance_of(str)])
  alias: str = attr.ib(None)

@attr.s(str=False, repr=False)
class Collector:
  '''Collector collects usage information about a piece of source code.
  
  This information is minimalist - it centers around identifying names and object usages. For
  example, this would track if the numpy library was imported, what it was aliased as (np), what
  functions were called and what were the types or values of the parameters.
  
  Ultimately, this collector extracts all the data used for training and making suggestions.'''
  # imported_modules = attr.ib(factory=list)
  modules_to_aliases = attr.ib(factory=partial(defaultdict, list))
  module_members = attr.ib(factory=list)

  def add_module_import(self, module, alias):
    self.modules_to_aliases[module].append(alias)  # defaultdict.

  def add_from_import(self, module, member, alias):
    self.module_members.append(ModuleMember(module, member, alias))

  def __str__(self):
    module_aliases_table = PrettyTable(['Module', 'Aliases'])
    for module, aliases in self.modules_to_aliases.items():
      module_aliases_table.add_row([module, str(aliases)])
    module_members_table = PrettyTable(['Module', 'Member', 'Alias'])
    for module_member in self.module_members:
      module_members_table.add_row([module_member.module, module_member.member, module_member.alias])
    return f'Imports:\n{module_aliases_table}\nMembers:\n{module_members_table}'
  # def process(self, cfg_node, curr_frame):
  #   if isinstance(cfg_node, ImportCfgNode):
  #     self.imported_modules.append(cfg_node.module_path)