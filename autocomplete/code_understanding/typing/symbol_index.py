import weakref
import itertools
import os
import sys
import types
import shutil
from collections import defaultdict
from enum import Enum
from functools import partial
from typing import (Dict, List)

import attr
import msgpack

from . import (control_flow_graph_nodes, errors, language_objects, module_loader, utils)
from .project_analysis.file_history_tracker import FileHistoryTracker
from .utils import is_python_file
from ...nsn_logging import info, warning
from ...trie import Trie


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
class _SymbolAlias:
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
    return _SymbolAlias(*args)


@attr.s(slots=True, hash=False, cmp=False)
class _InternalSymbolEntry:
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
    return _InternalSymbolEntry(*args)

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
class _LocationIndex:
  '''A data container for a SymbolIndex for a given location, e.g. directory & subdirs.

  Location generally refers to location as defined for modules in here:
  https://www.python.org/dev/peps/pep-0451/

  With the addition of a single 'Builtins' _LocationIndex.

  A subdir may take-over another _LocationIndex. For example:
  Give a set of paths: /a/{b,c,d}

  There may be a _LocationIndex for /a and /a/b. The former will handle all subdirs under /a
  except /a/b.

  This allows subpackages to have there own _LocationIndex when it's convenient (e.g. frequently
  updated packages contained on sys.path).
  
  TODO: Clean up this docstring.'''

  save_dir: str = attr.ib(kw_only=True)
  location: str = attr.ib(kw_only=True, validator=attr.validators.instance_of(str))
  symbol_dict = attr.ib(factory=partial(defaultdict, dict), kw_only=True)
  symbol_alias_dict = attr.ib(factory=partial(defaultdict, dict), kw_only=True)
  module_keys = attr.ib(factory=set, kw_only=True)
  is_file_location: bool = attr.ib(True, kw_only=True)
  _modified_since_save = attr.ib(False, init=False)
  # This is introducing a circular dependency - to avoid headaches with garbage collection breaking,
  # we use weakrefs here.
  _symbol_index_weakref: weakref = attr.ib(kw_only=True)
  _file_history_tracker: FileHistoryTracker = attr.ib(None, kw_only=True)
  _location_index_trie = attr.ib(None, kw_only=True)

  def __attrs_post_init__(self):
    if not os.path.exists(self.save_dir):
      os.makedirs(self.save_dir)

  @staticmethod
  def create_builtins_index(save_dir):
    index = _LocationIndex(save_dir=save_dir,
                           location='builtins',
                           is_file_location=False,
                           symbol_index_weakref=lambda: None)
    # Add builtins to symbol_dict by default to account for all builtin symbols since most modules
    # aren't going to do a "from builtins import *" explicitly.
    builtins_module_key = module_loader.ModuleKey(module_loader.ModuleSourceType.BUILTIN, 'builtins')
    index._add_module_by_key(builtins_module_key)
    for symbol in utils.get_possible_builtin_symbols():
      if symbol not in index.symbol_dict:
        index.symbol_dict[symbol][(builtins_module_key,
                                   False)] = _InternalSymbolEntry(SymbolType.UNKNOWN, builtins_module_key)
    return index

  @staticmethod
  def create_location_index(save_dir, target_directory, symbol_index):
    file_history_tracker = FileHistoryTracker.load(os.path.join(save_dir, 'fht.msg'))
    return _LocationIndex(save_dir=save_dir,
                          location=target_directory,
                          symbol_index_weakref=weakref.ref(symbol_index),
                          file_history_tracker=file_history_tracker)

  def find_symbol(self, symbol):
    for alias in self.symbol_alias_dict[symbol].values():
      symbol_entry = self.symbol_dict[alias.real_name][(alias.module_key, alias.is_module_itself)]
      yield CompleteSymbolEntry(symbol_entry, symbol, alias)
    for symbol_entry in self.symbol_dict[symbol].values():
      yield CompleteSymbolEntry(symbol_entry, symbol, None)

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
    serialized_module_key_list = [
        key.serialize() for key, _ in sorted(module_key_to_index_dict.items(), key=lambda kv: kv[1])
    ]

    return [self.location, d, alias_dict, serialized_module_key_list, self.is_file_location]

  @staticmethod
  def _deserialize(unpacked, save_dir, symbol_index):
    location, d, alias_dict, serialized_module_key_list, is_file_location = unpacked
    module_key_list = [
        module_loader.ModuleKey(module_loader.ModuleSourceType(type_), path)
        for type_, path in serialized_module_key_list
    ]
    symbol_dict = defaultdict(dict)
    for s, serialized_symbol_entries in d.items():
      module_key_symbol_entry_dict = {}
      for serialized_entry in serialized_symbol_entries:
        symbol_entry = _InternalSymbolEntry.deserialize(serialized_entry, module_key_list)
        module_key_symbol_entry_dict[(symbol_entry.module_key, symbol_entry.is_module_itself)] = symbol_entry
      symbol_dict[s] = module_key_symbol_entry_dict

    symbol_alias_dict = defaultdict(dict)
    for symbol, args_lists in alias_dict.items():
      alias_params_to_alias_dict = {}
      for args in args_lists:
        alias_params_to_alias_dict[tuple(args)] = _SymbolAlias.deserialize(args, module_key_list)
      symbol_alias_dict[symbol] = alias_params_to_alias_dict

    if is_file_location:
      file_history_tracker = FileHistoryTracker.load(os.path.join(save_dir, 'fht.msg'))
    else:
      file_history_tracker = None

    return _LocationIndex(save_dir=save_dir,
                          location=location,
                          symbol_dict=symbol_dict,
                          symbol_alias_dict=symbol_alias_dict,
                          module_keys=set(module_key_list),
                          is_file_location=is_file_location,
                          symbol_index_weakref=weakref.ref(symbol_index),
                          file_history_tracker=file_history_tracker)

  def save(self):
    if not self._modified_since_save:
      return

    info(f'Saving updates for {self.location}')
    if not os.path.exists(self.save_dir):
      os.makedirs(self.save_dir)
    with open(os.path.join(self.save_dir, 'index.msg'), 'wb') as f:
      msgpack.pack(self._serialize(), f, use_bin_type=True)

    self._file_history_tracker.save()
    self._modified_since_save = False

  def update(self, directory):
    if self.is_file_location:
      if len(directory) < len(self.location) and self.location[:len(directory)] == directory:
        filenames = self._file_history_tracker.get_files_in_dir_modified_since_timestamp(self.location)
      elif len(directory) > len(self.location) and directory[:len(self.location)] == self.location:
        filenames = self._file_history_tracker.get_files_in_dir_modified_since_timestamp(directory)
      else:
        return
      for filename in filenames:
        self.add_file(filename, check_timestamp=False)
      self._file_history_tracker.update_timestamp_for_path(self.location)

  @staticmethod
  def load(save_dir, symbol_index, readonly=False):
    filename = os.path.join(save_dir, 'index.msg')
    assert os.path.exists(filename)
    with open(filename, 'rb') as f:
      # use_list=False is better for performance reasons - tuples faster and lighter, but tuples
      # cannot be appended to and thus make the SymbolIndex essentially readonly.
      return _LocationIndex._deserialize(msgpack.unpack(f, raw=False, use_list=not readonly), save_dir,
                                         symbol_index)

  def add_path(self, path, include_private_files=False, track_imported_modules=False):
    assert os.path.exists(path)
    assert self.location == path[:len(self.location)]

    if not os.path.isdir(path):
      self.add_file(path, track_imported_modules)
      return

    # Always add to the location index that is closest to the path.
    check_descendent_index = self._location_index_trie and self._location_index_trie.has_children()
    if check_descendent_index:
      location_index = self._location_index_trie.get_most_recent_ancestor_or_actual(path).store_value()
      if id(location_index) != id(self):
        location_index.add_path(path, include_private_files, track_imported_modules)
        return

    location_indicies = [self] + list(
        self._location_index_trie.store_value_iter()) if check_descendent_index else [self]

    for location_index in location_indicies:
      full_filenames = location_index._file_history_tracker.get_files_in_dir_modified_since_timestamp(
          path, auto_update=True)
      for full_filename in full_filenames:
        if is_python_file(full_filename):
          self.add_file(full_filename,
                        track_imported_modules=track_imported_modules,
                        check_descendent_index=check_descendent_index)

    # path does not correspond with any individual _LocationIndex - put things in their places.
    # if ignore_init or os.path.exists(os.path.join(path, '__init__.py')):
    #   info(f'Adding dir: {path}')
    #   for filename in os.listdir(path):  # glob(os.path.join(path, '*.py')):
    #     full_filename = os.path.join(path, filename)
    #     if filename[-3:] == '.py':
    #       self.add_file(full_filename,
    #                     track_imported_modules=track_imported_modules,
    #                     check_descendent_index=check_descendent_index)
    #     elif os.path.isdir(filename):
    #       self.add_path(os.path.join(path, directory), track_imported_modules=track_imported_modules)

    # self._file_history_tracker.update_timestamp_for_path(path)

  def add_file(self,
               filename,
               *,
               track_imported_modules=False,
               check_descendent_index=True,
               check_timestamp=True):
    if not is_python_file(filename):
      return

    if check_timestamp and not self._file_history_tracker.has_file_changed_since_timestamp(filename):
      return

    module_key = module_loader.ModuleKey.from_filename(filename)
    self._add_module_by_key(module_key,
                            track_imported_modules=track_imported_modules,
                            check_descendent_index=check_descendent_index)
    self._file_history_tracker.update_timestamp_for_path(filename)
    self._modified_since_save = True  # File history changed if nothing else.

  def _add_module_by_key(self, module_key, track_imported_modules=False, check_descendent_index=True):
    if check_descendent_index and self._location_index_trie and self._location_index_trie.has_children():
      # We key on non-stub filenames
      filename = module_key.get_filename(prefer_stub=False)
      assert self.location == filename[:len(self.location)]
      # This will get the exact correct trie, regardless of how deep. store_value is a weakref.
      location_index = self._location_index_trie.get_most_recent_ancestor_or_actual(filename).store_value()
      return location_index._add_module_by_key(module_key,
                                               track_imported_modules,
                                               check_descendent_index=False)

    # Note that we explicity do this here instead of in _add_module_by_key as the latter may have
    # already been done without tracking the module's contents and would thus return early.
    module = None

    if track_imported_modules and not module_key.is_bad():
      module_loader.keep_graphs_default = True
      module = module_loader.get_module_from_key(module_key, lazy=False, include_graph=True)
      assert not module.module_type == language_objects.ModuleType.UNKNOWN_OR_UNREADABLE
      assert module.graph
      directory = os.path.dirname(module.filename)
      self._process_tracked_imports(module_key, module.graph, directory)

    if module_key in self.module_keys:
      warning(f'Skipping {module_key} - already processed.')
      return False

    info(f'Adding to index: {module_key}')
    module = module if module else module_loader.get_module_from_key(
        module_key, lazy=False, include_graph=False)
    self._add_module(module, module_key)
    self.module_keys.add(module_key)
    self.symbol_dict[module_key.get_module_basename()][(module_key,
                                                        True)] = _InternalSymbolEntry(SymbolType.MODULE,
                                                                                      module_key,
                                                                                      is_module_itself=True)
    self._modified_since_save = True
    if track_imported_modules:
      module_loader.keep_graphs_default = False
    return True

  def _add_module(self, module, module_key):
    for name, member in filter(lambda kv: _should_export_symbol(module, *kv), module.items()):
      try:
        entry = self.symbol_dict[name][(module_key, False)] = _InternalSymbolEntry(
            SymbolType.from_pobject_value(member.value()), module_key, imported=member.imported)
      except errors.AmbiguousFuzzyValueError:
        entry = self.symbol_dict[name][(module_key, False)] = _InternalSymbolEntry(SymbolType.AMBIGUOUS,
                                                                                   module_key,
                                                                                   imported=member.imported)

  def _process_tracked_imports(self, source_module_key, graph, source_dir):
    # TODO: Consider combining with other modules to avoid repeated symbol_entry lookups.
    symbol_index = self._symbol_index_weakref()
    if not symbol_index:
      warning(f'Hmm, symbol_index ref died... Generally, this shouldn\'t be reachable.')
      return

    imported_module_key_to_value_as_names = _track_modules(graph, source_dir)
    existing_module_key_to_value_as_name_dict = self._load_existing_module_value_as_names(source_module_key)

    symbol_use_changed = False
    for module_key, value_as_name_list in imported_module_key_to_value_as_names.items():
      symbol_index._add_module_by_key(module_key)
      location_index = symbol_index._get_location_index_for_module_key(module_key)
      symbol_dict = location_index.symbol_dict
      symbol_alias_dict = location_index.symbol_alias_dict
      existing_value_as_name_set = existing_module_key_to_value_as_name_dict[module_key]
      changed = False
      for value, as_name in value_as_name_list:
        if (value, as_name) in existing_value_as_name_set:
          existing_value_as_name_set.remove((value, as_name))
          continue
        changed = True
        # Not already added - add to symbol entry.
        _update_symbol(symbol_dict, symbol_alias_dict, module_key, value, as_name, 1)
      # Remove any symbols that are no longer present in the file.
      for value, as_name in existing_value_as_name_set:
        _update_symbol(location_index, module_key, value, as_name, -1)
      # Determine if the symbols imported by the module have changed - update if so.
      if changed or existing_value_as_name_set:
        existing_module_key_to_value_as_name_dict[module_key] = set(value_as_name_list)
        symbol_use_changed = True
    if symbol_use_changed:
      # Darn, need to persist.
      self._save_existing_module_value_as_names(source_module_key, existing_module_key_to_value_as_name_dict)

  def _load_existing_module_value_as_names(self, module_key):
    # TODO: Make this async & start load before doing anything with the module to get higher
    # CPU utilization.
    # The individual file-overhead for msg-pack is surprisingly small compared to the linear
    # cost of increasing file sizes. Since we need this data typically only for a small subset of
    # the files (essentially only modified), it makes more sense to store these separately.
    filename = self._get_existing_module_value_as_names_filename(module_key)
    if not os.path.exists(filename):
      return defaultdict(set)

    with open(filename, 'rb') as f:
      d = msgpack.unpack(f, use_list=False, raw=False)
      return defaultdict(set, {k: set(v) for k, v in d.items()})

  def _save_existing_module_value_as_names(self, module_key, existing_module_value_as_names):
    # TODO: Make this async & start load before doing anything with the module to get higher
    # CPU utilization.
    # The individual file-overhead for msg-pack is surprisingly small compared to the linear
    # cost of increasing file sizes. Since we need this data typically only for a small subset of
    # the files (essentially only modified), it makes more sense to store these separately.
    with open(self._get_existing_module_value_as_names_filename(module_key), 'wb') as f:
      d = {k.serialize(): tuple(v) for k, v in existing_module_value_as_names.items()}
      msgpack.pack(d, f, use_bin_type=True)

  def _get_existing_module_value_as_names_filename(self, module_key):
    return os.path.join(self.save_dir, f'{str(hash(module_key))}.msg')


def _update_symbol(symbol_dict, symbol_alias_dict, module_key, value, as_name, count_delta):
  real_name = value if value else module_key.get_module_basename()
  is_module_itself = False if value else True
  key = (module_key, is_module_itself)
  entry = symbol_dict[real_name][key]
  entry.import_count += 1
  if as_name:
    symbol_alias_count_dict = symbol_alias_dict[as_name]
    args = (real_name, module_key, is_module_itself)
    if args in symbol_alias_count_dict:
      symbol_alias_count_dict[args].import_count += 1
    else:
      symbol_alias_count_dict[args] = _SymbolAlias(*args, import_count=1)


def _track_modules(graph, source_dir):
  import_nodes = graph.get_descendents_of_types(
      (control_flow_graph_nodes.ImportCfgNode, control_flow_graph_nodes.FromImportCfgNode))
  imported_module_key_to_value_as_names = defaultdict(list)
  for node in import_nodes:
    if isinstance(node, control_flow_graph_nodes.ImportCfgNode):
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
            module_loader.join_module_attribute(node.module_path, value), source_dir)
        if module_key.module_source_type != module_loader.ModuleSourceType.BAD:
          value = None
        else:
          module_key = None
      if not module_key:
        module_key = module_loader.get_module_info_from_name(node.module_path, source_dir)[0]
      if module_key.module_source_type != module_loader.ModuleSourceType.BAD:
        imported_module_key_to_value_as_names[module_key].append((value, as_name))
  return imported_module_key_to_value_as_names


@attr.s(slots=True)
class SymbolIndex:
  save_dir = attr.ib()
  _builtins_location_index = attr.ib()
  _location_indicies = attr.ib(factory=list)
  # This just mirrors the list above (minus builtin), but is more efficient for certain operations.
  _file_location_indicies_trie = attr.ib(factory=Trie)
  _module_key_to_location_index_dict = attr.ib(factory=dict)
  _failed_module_keys = attr.ib(factory=set)

  def find_symbol(self, symbol):
    yield from itertools.chain(*[index.find_symbol(symbol) for index in self._location_indicies])

  def _serialize(self):
    return [module_key.serialize() for module_key in self._failed_module_keys]

  @staticmethod
  def _deserialize(unpacked):
    return [module_loader.ModuleKey.deserialize(serialized_mk) for serialized_mk in unpacked]

  def save(self):
    for index in self._location_indicies:
      index.save()
    with open(os.path.join(self.save_dir, 'failed.msg'), 'wb') as f:
      msgpack.pack(self._serialize(), f, use_bin_type=True)

  @staticmethod
  def load(save_dir, readonly=False):
    if not os.path.exists(save_dir):
      raise ValueError(save_dir)

    with open(os.path.join(save_dir, 'failed.msg'), 'rb') as f:
      # use_list=False is better for performance reasons - tuples faster and lighter, but tuples
      # cannot be appended to and thus make the SymbolIndex essentially readonly.
      failed_module_keys = SymbolIndex._deserialize(msgpack.unpack(f, raw=False, use_list=not readonly))

    location_indicies = []
    module_key_to_location_index_dict = {}
    index = SymbolIndex(save_dir,
                        None,
                        location_indicies,
                        module_key_to_location_index_dict=module_key_to_location_index_dict,
                        failed_module_keys=failed_module_keys)
    for filename in os.listdir(save_dir):
      full_filename = os.path.join(save_dir, filename)
      if os.path.isdir(full_filename):
        if not os.path.exists(os.path.join(full_filename, 'index.msg')):
          continue
        location_index = _LocationIndex.load(full_filename, index)
        location_indicies.append(location_index)
        if not location_index.is_file_location:
          index._builtins_location_index = location_index
        for mk in location_index.module_keys:
          module_key_to_location_index_dict[mk] = location_index

    trie = Trie()
    # Note: order doesn't matter since returned Tries are stable.
    for location_index in filter(lambda x: x.is_file_location, location_indicies):
      location_index._location_index_trie = trie.add(location_index.location,
                                                     value=0,
                                                     store_value=weakref.ref(location_index))

    index._file_location_indicies_trie = trie
    return index

  # TODO:
  # @staticmethod
  # def build_complete_index(save_dir):
  #   index = SymbolIndex.create_index(save_dir)
  #   for path in sys.path:
  #     index.add_path(path, ignore_init=True)

  #   return index

  @staticmethod
  def create_index(save_dir):
    if not os.path.exists(save_dir):
      os.makedirs(save_dir)
    builtins_location_index = _LocationIndex.create_builtins_index(
        SymbolIndex._get_location_save_dir_from_main_dir(save_dir, 'builtins'))
    index = SymbolIndex(save_dir, builtins_location_index)
    index._location_indicies.append(builtins_location_index)
    for path in sys.path:
      index._get_or_add_location_index_for_dir(path)

    return index

  @staticmethod
  def build_index_from_package(package_path, save_dir, clean=False):
    # TODO: Use this as a marking-mechanism perhaps - i.e. do as this is doing now, but explicitly
    # allow marking 'packages of interest' so it's not always about building a new index - instead,
    # a different project may care about the same one.
    assert os.path.exists(package_path)
    index = None
    if os.path.exists(save_dir):
      if clean:
        shutil.rmtree(save_dir)
      else:
        index = SymbolIndex.load(save_dir)
        # TODO: check that package_path is in _location_indicies...
    if not index:
      index = SymbolIndex.create_index(save_dir)

    index.add_path(package_path, track_imported_modules=True)
    index.save()
    return index

  @staticmethod
  def _get_location_save_dir_from_main_dir(save_dir, location_name):
    return os.path.join(save_dir, str(hash(location_name)))

  def _get_location_save_dir(self, location_name):
    return SymbolIndex._get_location_save_dir_from_main_dir(self.save_dir, str(hash(location_name)))

  def _get_or_add_location_index_for_dir(self, directory):
    location_index = self._get_location_index_for_filename(dir_w_sep(directory))
    if location_index:
      # assert location_index.location == directory  # TODO: Support splitting _LocationIndicies.
      return location_index

    # Doesn't exist - create.
    location_index = _LocationIndex.create_location_index(self._get_location_save_dir(directory), directory,
                                                          self)
    self._location_indicies.append(location_index)
    self._file_location_indicies_trie.add(dir_w_sep(directory), value=0, store_value=location_index)
    return location_index

  def _get_location_index_for_module_key(self, module_key):
    if module_key in self._module_key_to_location_index_dict:
      return self._module_key_to_location_index_dict[module_key]

    if module_key.is_bad():
      return None

    if module_key.module_source_type == module_loader.ModuleSourceType.BUILTIN:
      return self._builtins_location_index

    filename = module_key.get_filename()
    return self._get_location_index_for_filename(filename)

  def _get_location_indicies_for_dir(self, directory):
    trie = self._file_location_indicies_trie.get_most_recent_ancestor_or_actual(dir_w_sep(directory))
    if trie:
      for value in trie.store_value_iter():
        yield value()  # weakref.
    return []

  def _get_location_index_for_filename(self, filename):
    if os.path.isdir(filename):
      filename = dir_w_sep(filename)
    trie = self._file_location_indicies_trie.get_most_recent_ancestor_or_actual(filename)
    if trie:
      return trie.store_value()
    return None

  def update(self, directory):
    # If dir is lower than multiple indicies, multiple indicies may be associated with it.
    location_indicies = self._get_location_indicies_for_dir(directory)
    # If it's fully contained in an index, the above will be empty - get the lone index then.
    if not location_indicies:
      location_indicies = [self._get_location_index_for_filename(directory)]
    for location_index in location_indicies:
      location_index.update(directory)

  def add_path(self, path, include_private_files=False, track_imported_modules=False):
    assert os.path.exists(path)
    if not os.path.isdir(path):
      self.add_file(path, track_imported_modules)
      return

    location_index = self._get_or_add_location_index_for_dir(path)

    location_index.add_path(path,
                            include_private_files=include_private_files,
                            track_imported_modules=track_imported_modules)

  def add_file(self, filename, track_imported_modules=False):
    module_key = module_loader.ModuleKey.from_filename(filename)
    self._add_module_by_key(module_key, track_imported_modules=track_imported_modules)

  def _add_module_by_key(self, module_key, track_imported_modules=False):
    if module_key.is_bad():
      self._failed_module_keys.append(module_key)
      return
    location_index = self._get_location_index_for_module_key(module_key)
    assert location_index
    newly_added = location_index._add_module_by_key(module_key, track_imported_modules)
    if newly_added:
      self._module_key_to_location_index_dict[module_key] = location_index
    return location_index


def _should_export_symbol(current_module, name, pobject):
  if name == '_' or name[:2] == '__':
    return False

  # TODO: Include, but possibly penalize later.
  # if pobject.imported:
  #   return False

  if isinstance(pobject, language_objects.Module):
    return False

  return True


# TODO: Merge w/FHT logic. FilePathTrie?
def dir_w_sep(directory):
  if directory[-1] == os.sep:
    return directory
  return f'{directory}{os.sep}'


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
