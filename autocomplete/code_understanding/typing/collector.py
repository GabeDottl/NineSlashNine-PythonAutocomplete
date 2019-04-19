import os
from collections import defaultdict
from functools import partial

import attr
from prettytable import PrettyTable

# TODO: Dict on type?
_filename_context = []
_block_context = []  # Module, Function, Klass
_parso_node_context = []
_missing_symbols = defaultdict(list)


def get_current_context_dir():
  return os.path.get_dir(_filename_context[-1])


@attr.s
class FileContext:
  filename = attr.ib()

  def __enter__(self):
    _filename_context.append(self.filename)

  def __exit__(self, exc_type, exc_value, traceback):
    _filename_context.pop()


def paths_prefix():
  filenames = [os.path.basename(path) for path in _filename_context]
  return '|'.join(filenames)


@attr.s
class BlockContext:
  block = attr.ib()

  def __enter__(self):
    _block_context.append(self.block)

  def __exit__(self, exc_type, exc_value, traceback):
    _block_context.pop()


@attr.s
class ParsoNodeContext:
  parso_node = attr.ib()

  def __enter__(self):
    _parso_node_context.append(self.parso_node)

  def __exit__(self, exc_type, exc_value, traceback):
    _parso_node_context.pop()


def get_code_context_string():
  filename = _filename_context[-1] if _filename_context else ''
  if _parso_node_context:
    node = _parso_node_context[-1]
    code = node.get_code().strip()
    line = node.start_pos[0]
    if filename:
      return f'"{filename}", line {line}, ({code})'
    return 'line {line}, ({code})'
    # out = f'{node.start_pos}:{node.get_code()}'
  return filename


def add_missing_symbol(name):
  assert _filename_context
  _missing_symbols[_filename_context[-1]].append(name)


def get_missing_symbols_in_file(filename):
  return _missing_symbols[filename]


@attr.s  #(frozen=True)
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
  class_defs = attr.ib(factory=list)
  function_defs = attr.ib(factory=list)
  variable_assignments = attr.ib(factory=list)
  functions = attr.ib(factory=list)

  def add_module_import(self, module, alias):
    self.modules_to_aliases[module].append(alias)  # defaultdict.

  def add_from_import(self, module, member, alias):
    self.module_members.append(ModuleMember(module, member, alias))

  def add_variable_assignment(self, variable_name, code):
    self.variable_assignments.append((variable_name, code))  # TODO: Wrap.

  def add_function_node(self, function_node):
    self.functions.append(function_node)

  # def add_class_def(self, class_name, member, alias):
  #   self.module_members.append(ModuleMember(module, member, alias))

  # def add_from_import(self, module, member, alias):
  #   self.module_members.append(ModuleMember(module, member, alias))

  def __str__(self):
    module_aliases_table = PrettyTable(['Module', 'Aliases'])
    for module, aliases in self.modules_to_aliases.items():
      module_aliases_table.add_row([module, str(aliases)])
    module_members_table = PrettyTable(['Module', 'Member', 'Alias'])
    for module_member in self.module_members:
      module_members_table.add_row(
          [module_member.module, module_member.member, module_member.alias])
    assignments_table = PrettyTable(['Name', 'Code'])
    for name, code in self.variable_assignments:
      assignments_table.add_row([name, code])

    return f'Imports:\n{module_aliases_table}\nMembers:\n{module_members_table}\nVariables:\n{assignments_table}'

  # def process(self, cfg_node, curr_frame):
  #   if isinstance(cfg_node, ImportCfgNode):
  #     self.imported_modules.append(cfg_node.module_path)
