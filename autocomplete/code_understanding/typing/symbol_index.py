import builtins
import os
import sys
import types
from collections import defaultdict
from enum import Enum
from functools import partial
from glob import glob
from typing import Dict, List, Tuple

import attr
import msgpack

from . import (control_flow_graph_nodes, errors, language_objects, module_loader, utils)
from ...nsn_logging import info, warning


class SymbolType(Enum):
  TYPE = 0
  FUNCTION = 1
  ASSIGNMENT = 2
  MODULE = 3
  UNKNOWN = 4
  AMBIGUOUS = 5

  @staticmethod
  def from_pobject_value(value):
    if isinstance(value, language_objects.Klass):
      return SymbolType.TYPE
    if isinstance(value, language_objects.Function):
      return SymbolType.FUNCTION
    if isinstance(value, language_objects.Instance):
      return SymbolType.ASSIGNMENT
    if isinstance(value, language_objects.Module):
      return SymbolType.MODULE
    return SymbolType.from_real_obj(value)

  @staticmethod
  def from_real_obj(obj):
    type_ = type(obj)
    if isinstance(type_, (bool, str, int, float, type(None))):
      return SymbolType.ASSIGNMENT
    if isinstance(type_, type):
      return SymbolType.TYPE
    if isinstance(type_, (types.BuiltinMethodType, types.FunctionType, types.BuiltinFunctionType)):
      return SymbolType.FUNCTION
    return SymbolType.UNKNOWN


@attr.s(slots=True, hash=False, cmp=False)
class SymbolAlias:
  real_name = attr.ib()
  module_key = attr.ib()
  is_module_itself: bool = attr.ib()
  import_count: int = attr.ib(0)

  def serialize(self, module_key_to_index_dict):
    args = list(attr.astuple(self, recurse=False))  # recurse=False - don't apply to ModuleKey.
    args[1] = module_key_to_index_dict[args[1]]
    return args

  @staticmethod
  def deserialize(tuple_, module_key_list):
    args = list(tuple_)
    args[1] = module_key_list[args[1]]
    return SymbolAlias(*args)


@attr.s(slots=True, hash=False, cmp=False)
class InternalSymbolEntry:
  '''This class stores information about module symbols in a format convenient for serialization.

  It generally should not be exposed through any public APIs outside of this file.
  '''
  symbol_type: SymbolType = attr.ib()
  module_key: module_loader.ModuleKey = attr.ib()
  # symbol_meta = attr.ib(None)
  is_module_itself: bool = attr.ib(False)
  imported: bool = attr.ib(False)
  import_count: int = attr.ib(0)

  def serialize(self, module_key_to_index_dict):
    args = list(attr.astuple(self, recurse=False))  # recurse=False - don't apply to ModuleKey.
    args[0] = args[0].value  # symbol_type
    args[1] = module_key_to_index_dict[args[1]]
    return args

  @staticmethod
  def deserialize(tuple_, module_key_list):
    args = list(tuple_)
    args[0] = SymbolType(args[0])
    args[1] = module_key_list[args[1]]
    return InternalSymbolEntry(*args)

  def is_from_native_module(self):
    return self.module_type == language_objects.ModuleType.BUILTIN


@attr.s(str=False, repr=False)
class CompleteSymbolEntry:
  '''This class represents a complete symbol entry including all APIs necessary for importing the
  symbol and getting info about it without needing to know internal details like whether or not it's
  an alias and such.
  '''
  _internal_symbol_entry = attr.ib()
  symbol_name = attr.ib()
  _symbol_alias = attr.ib(None)

  def get_symbol_type(self):
    return self._internal_symbol_entry.symbol_type

  def get_module_key(self):
    return self._internal_symbol_entry.module_key

  def is_module_itself(self):
    return self._internal_symbol_entry.is_module_itself

  def is_imported(self):
    return self._internal_symbol_entry.imported

  def get_import_count(self):
    if self._symbol_alias:
      return self._symbol_alias.import_count
    return self._internal_symbol_entry.import_count

  def get_real_name(self):
    return self._symbol_alias.real_name if self._symbol_alias else self.symbol_name

  def is_alias(self):
    return self._symbol_alias is not None

  def __str__(self):
    return f'({self.get_module_key()}, {self.get_real_name() if not self.is_module_itself() else None}, {self.symbol_name})'

  def __repr__(self):
    return f'({self.get_module_key()}, {self.get_real_name() if not self.is_module_itself() else None}, {self.symbol_name})'


def pretty_print_symbol_entries(symbol_entries):
  for symbol_entry in symbol_entries:
    print(symbol_entry)


@attr.s
class SymbolIndex:
  save_path = attr.ib(None)
  symbol_dict = attr.ib(factory=partial(defaultdict, dict))
  symbol_alias_dict = attr.ib(factory=partial(defaultdict, dict))

  module_keys = attr.ib(factory=set)

  failed_module_keys = attr.ib(factory=set)
  num_files_added = attr.ib(0, init=False)

  # Key is: (module_key,from_import_value, as_name)
  value_module_reference_map: Dict[Tuple[module_loader.ModuleKey, str, str], int] = attr.ib(factory=partial(
      defaultdict, int),
                                                                                            init=False)

  def __attrs_post_init__(self):
    if not len(self.symbol_dict):
      # Add builtins to symbol_dict by default if it's not been initialized with some set.
      builtins_module_key = module_loader.ModuleKey(module_loader.ModuleSourceType.BAD, 'fake_builtins_module')
      self.module_keys.add(builtins_module_key)
      for symbol, value in builtins.__dict__.items():
        self.symbol_dict[symbol][(builtins_module_key, False)] = InternalSymbolEntry(SymbolType.from_real_obj(value), builtins_module_key)
      for symbol in utils.get_possible_builtin_symbols():
        if symbol not in self.symbol_dict:
          self.symbol_dict[symbol][(builtins_module_key, False)] = InternalSymbolEntry(SymbolType.UNKNOWN, builtins_module_key)

  def find_symbol(self, symbol):
    for alias in self.symbol_alias_dict[symbol].values():
      symbol_entry = self.symbol_dict[alias.real_name][(alias.module_key, alias.is_module_itself)]
      yield CompleteSymbolEntry(symbol_entry, symbol, alias)
    for symbol_entry in self.symbol_dict[symbol].values():
      yield CompleteSymbolEntry(symbol_entry, symbol, None)

  def get_modules_for_symbol_entries(self, symbol_entries):
    for symbol_entry in symbol_entries:
      yield symbol_entry, self.module_key_list[symbol_entry.module_key]

  def _serialize(self):
    d = {}
    alias_dict = {}
    module_key_to_index_dict = {mk: i for i, mk in enumerate(self.module_keys)}
    for symbol, module_key_symbol_entry_dict in self.symbol_dict.items():
      d[symbol] = [v.serialize(module_key_to_index_dict) for v in module_key_symbol_entry_dict.values()]

    for symbol, alias_params_to_alias_dict in self.symbol_alias_dict.items():
      aliases = alias_params_to_alias_dict.values()
      l = alias_dict[symbol] = []
      for alias in aliases:
        l.append(alias.serialize(module_key_to_index_dict))
    serialized_module_key_list = [key.serialize() for key, _ in sorted(module_key_to_index_dict.items(), key=lambda kv: kv[1])]
    serialized_failed_module_key_list = [key.serialize() for key in self.failed_module_keys]
    return [d, alias_dict, serialized_module_key_list, serialized_failed_module_key_list]

  @staticmethod
  def _deserialize(unpacked):
    d, alias_dict, serialized_module_key_list, failed_module_keys_list = unpacked
    module_key_list = [
        module_loader.ModuleKey(module_loader.ModuleSourceType(type_), path)
        for type_, path in serialized_module_key_list
    ]
    symbol_dict = defaultdict(dict)
    for s, serialized_symbol_entries in d.items():
      module_key_symbol_entry_dict = {}
      for serialized_entry in serialized_symbol_entries:
        # TODO: Need to match this!!!!!!
        symbol_entry = InternalSymbolEntry.deserialize(serialized_entry, module_key_list)
        module_key_symbol_entry_dict[(symbol_entry.module_key,
                                        symbol_entry.is_module_itself)] = symbol_entry
      symbol_dict[s] = module_key_symbol_entry_dict

    symbol_alias_dict = defaultdict(dict)
    for symbol, args_lists in alias_dict.items():
      alias_params_to_alias_dict = {}
      for args in args_lists:
        alias_params_to_alias_dict[tuple(args)] = SymbolAlias.deserialize(args, module_key_list)
      symbol_alias_dict[symbol] = alias_params_to_alias_dict

    return SymbolIndex(symbol_dict=symbol_dict,
                       symbol_alias_dict=symbol_alias_dict,
                       module_keys=set(module_key_list),
                       failed_module_keys=set(*failed_module_keys_list))

  @staticmethod
  def load(filename, readonly=False):
    with open(filename, 'rb') as f:
      # use_list=False is better for performance reasons - tuples faster and lighter, but tuples
      # cannot be appended to and thus make the SymbolIndex essentially readonly.
      out = SymbolIndex._deserialize(msgpack.unpack(f, raw=False, use_list=not readonly))
    out.save_path = filename
    return out

  def save(self):
    with open(self.save_path, 'wb') as f:
      msgpack.pack(self._serialize(), f, use_bin_type=True)

  @staticmethod
  def build_index(target_index_filename):
    index = SymbolIndex(target_index_filename)
    for path in sys.path:
      index.add_path(path, ignore_init=True)
    return index

  @staticmethod
  def build_index_from_package(package_path, target_index_filename):
    assert os.path.exists(package_path)
    index = SymbolIndex(target_index_filename)
    index.add_path(package_path, ignore_init=True, track_imported_modules=True)
    index.process_tracked_imports()
    return index

  def update_index_from_package(self, package_path):
    assert os.path.exists(package_path)
    self.add_path(package_path, ignore_init=True, track_imported_modules=True)
    self.process_tracked_imports()

  def process_tracked_imports(self):
    for (module_key, value, as_name), count in self.value_module_reference_map.items():
      if module_key.module_source_type == module_loader.ModuleSourceType.BAD:
        continue

      self.add_module_by_key(module_key)

      real_name = value if value else module_key.get_module_basename()
      module_key_symbol_entry_dict = self.symbol_dict[real_name]
      is_module_itself = not value

      key = (module_key, is_module_itself)
      # TODO: Dynamically add if this fails.
      assert key in module_key_symbol_entry_dict
      entry = module_key_symbol_entry_dict[key]
      entry.import_count += count

      if as_name:
        symbol_alias_count_dict = self.symbol_alias_dict[as_name]
        args = (real_name, module_key, is_module_itself)
        if args in symbol_alias_count_dict:
          symbol_alias_count_dict[args].import_count += 1
        else:
          symbol_alias_count_dict[args] = SymbolAlias(*args, import_count=1)
    info(f'Processed tracked imports; clearing.')
    self.value_module_reference_map.clear()

  def add_path(self, path, ignore_init=False, include_private_files=False, track_imported_modules=False):
    if not os.path.exists(path):
      return

    if track_imported_modules:
      module_loader.keep_graphs_default = True
    init_file = os.path.join(path, '__init__.py')
    if ignore_init or os.path.exists(init_file):
      info(f'Adding dir: {path}')
      for filename in glob(os.path.join(path, '*.py')):
        self.add_file(filename, track_imported_modules=track_imported_modules)
      for directory in filter(lambda p: os.path.isdir(os.path.join(path, p)), os.listdir(path)):
        self.add_path(os.path.join(path, directory), track_imported_modules=track_imported_modules)
    if track_imported_modules:
      module_loader.keep_graphs_default = False

  def _track_modules(self, graph, directory):
    import_nodes = graph.get_descendents_of_types(
        (control_flow_graph_nodes.ImportCfgNode, control_flow_graph_nodes.FromImportCfgNode))
    imported_symbols_and_modules = []
    for node in import_nodes:
      if isinstance(node, control_flow_graph_nodes.ImportCfgNode):
        if 'attr' in node.module_path:
          info(f'import attr')
        value_and_as_names = [(None, node.as_name)]
      else:
        value_and_as_names = node.from_import_name_alias_dict.items()
      for value, as_name in value_and_as_names:
        module_key = None
        if value:
          if value == '*':
            # Don't try to track wild-card imports. Reduces complexity a bit.
            continue
          # Check if from import value is a module itself - if so, put it into the module key and
          # remove the value.
          module_key, _, module_type = module_loader.get_module_info_from_name(
              module_loader.join_module_attribute(node.module_path, value), directory)
          if module_key.module_source_type != module_loader.ModuleSourceType.BAD:
            value = None
          else:
            module_key = None
        if not module_key:
          module_key = module_loader.get_module_info_from_name(node.module_path, directory)[0]

        imported_symbols_and_modules.append((module_key, value, as_name))
    for module_key_value_as_name in imported_symbols_and_modules:
      self.value_module_reference_map[module_key_value_as_name] += 1

  def add_file(self, filename, track_imported_modules=False):
    try:
      module_key = module_loader.ModuleKey.from_filename(filename)
    except ValueError:
      return

    # Note that we explicity do this here instead of in add_module_by_key as the latter may have
    # already been done without tracking the module's contents and would thus return early.
    if track_imported_modules:
      module = module_loader.get_module_from_key(module_key, lazy=False, include_graph=True)
      if module.module_type == language_objects.ModuleType.UNKNOWN_OR_UNREADABLE:
        info(f'Failed on {module_key} - unreadable')
        self.failed_module_keys.add(module_key)
        return
      assert module.graph
      directory = os.path.dirname(module.filename)
      self._track_modules(module.graph, directory)

    return self.add_module_by_key(module_key)

  def add_module_by_key(self, module_key):
    if module_key in self.module_keys or module_key in self.failed_module_keys:
      warning(f'Skipping {module_key} - already processed.')
      return
    # filename = module_key.get_filename() if module_key.module_source_type != module_loader.ModuleSourceType.BUILTIN else None
    info(f'Adding to index: {module_key}')
    try:
      module = module_loader.get_module_from_key(module_key, lazy=False, include_graph=False)
      self.add_module(module, module_key)
    except OSError as e:  # Exception
      info(f'Failed on {module_key}: {e}')
      self.failed_module_keys.add(module_key)
    else:
      self.module_keys.add(module_key)
      self.num_files_added += 1
      self.symbol_dict[module_key.get_module_basename()][(module_key,
                                                          True)] = InternalSymbolEntry(SymbolType.MODULE,
                                                                                       module_key,
                                                                                       is_module_itself=True)

  def add_module(self, module, module_key):
    for name, member in filter(lambda kv: _should_export_symbol(module, *kv), module.items()):
      try:
        entry = self.symbol_dict[name][(module_key, False)] = InternalSymbolEntry(
            SymbolType.from_pobject_value(member.value()), module_key, imported=member.imported)
      except errors.AmbiguousFuzzyValueError:
        entry = self.symbol_dict[name][(module_key, False)] = InternalSymbolEntry(SymbolType.AMBIGUOUS,
                                                                                    module_key,
                                                                                    imported=member.imported)
      # self.module_to_symbols_dict[module_key].append(entry)


def _should_scan_file(filename, include_private_files):
  if include_private_files:
    return True
  return filename[0] != '_'


def _should_export_symbol(current_module, name, pobject):
  if name == '_' or name[:2] == '__':
    return False

  # TODO: Include, but possibly penalize later.
  # if pobject.imported:
  #   return False

  if isinstance(pobject, language_objects.Module):
    return False

  return True


def base_module_name(module_name):
  if '.' not in module_name:
    return module_name
  else:
    return module_name[:module_name.find('.')]


def main(target_package, output_path):
  assert os.path.exists(target_package)
  index = SymbolIndex.build_index_from_package(target_package, output_path)
  index.save()


if __name__ == "__main__":
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('target_package')
  parser.add_argument('output_path')
  args, _ = parser.parse_known_args()
  main(args.target_package, args.output_path)
