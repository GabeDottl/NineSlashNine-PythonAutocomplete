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
_referenced_symbols = defaultdict(set)

_modules_to_aliases = defaultdict(partial(defaultdict, list))
_module_members = defaultdict(list)
_class_defs = defaultdict(list)
_function_defs = defaultdict(list)
_variable_assignments = defaultdict(list)
_functions = defaultdict(list)


def get_current_context_dir():
  return os.path.split(_filename_context[-1])[0]


@attr.s(slots=True)
class FileContext:
  filename = attr.ib()

  def __enter__(self):
    _filename_context.append(self.filename)

  def __exit__(self, exc_type, exc_value, traceback):
    _filename_context.pop()


def paths_prefix():
  filenames = [os.path.basename(path) for path in _filename_context]
  return '|'.join(filenames)


@attr.s(slots=True)
class BlockContext:
  block = attr.ib()

  def __enter__(self):
    _block_context.append(self.block)

  def __exit__(self, exc_type, exc_value, traceback):
    _block_context.pop()


@attr.s(slots=True)
class ParsoNodeContext:
  parso_node = attr.ib()

  def __enter__(self):
    _parso_node_context.append(self.parso_node)

  def __exit__(self, exc_type, exc_value, traceback):
    _parso_node_context.pop()


def get_current_parso_node():
  return _parso_node_context[-1]


def add_missing_symbol(filename, name, context):
  _missing_symbols[filename].append((name, context))


def add_referenced_symbol(filename, name):
  _referenced_symbols[filename].add(name)


def get_missing_symbols_in_file(filename, include_context=True):
  if include_context:
    return _missing_symbols[filename]
  else:
    return set(a[0] for a in _missing_symbols[filename])


@attr.s(slots=True)
class ModuleMember:
  module: str = attr.ib(validator=[attr.validators.instance_of(str)])
  member: str = attr.ib(validator=[attr.validators.instance_of(str)])
  alias: str = attr.ib(None)


def add_module_import(module, alias):
  _modules_to_aliases[_filename_context[-1]][module].append(
      alias)  # defaultdict.


def add_from_import(module, member, alias):
  _module_members[_filename_context[-1]].append(
      ModuleMember(module, member, alias))


def add_variable_assignment(variable_name, code):
  _variable_assignments[_filename_context[-1]].append(
      (variable_name, code))  # TODO: Wrap.


def add_function_node(function_node):
  _functions[_filename_context[-1]].append(function_node)


def print_stats(self):
  module_aliases_table = PrettyTable(['Module', 'Aliases'])
  for module, aliases in _modules_to_aliases.items():
    module_aliases_table.add_row([module, str(aliases)])
  module_members_table = PrettyTable(['Module', 'Member', 'Alias'])
  for module_member in _module_members:
    module_members_table.add_row(
        [module_member.module, module_member.member, module_member.alias])
  assignments_table = PrettyTable(['Name', 'Code'])
  for name, code in _variable_assignments:
    assignments_table.add_row([name, code])

  return f'Imports:\n{module_aliases_table}\nMembers:\n{module_members_table}\nVariables:\n{assignments_table}'
