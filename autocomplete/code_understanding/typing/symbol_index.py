'''This module stores an index of modules symbols and metadata.

Note: in general, os.path.abspath is preferred over pathlib.Path due to the dramatic performance
difference between the two:

CPU times: user 249 µs, sys: 10 µs, total: 259 µs
Wall time: 214 µs
Out[50]: PosixPath('/asdf')

In [52]: %time os.path.abspath('/asdf/')
CPU times: user 10 µs, sys: 1e+03 ns, total: 11 µs
Wall time: 12.6 µs
Out[52]: '/asdf'

'''
import weakref
import itertools
import os
import sys
import types
import shutil
from collections import defaultdict
from enum import Enum
from functools import partial

import attr
import msgpack

from . import (control_flow_graph_nodes, errors, language_objects, module_loader, utils)
from .project_analysis.file_history_tracker import FileHistoryTracker, python_package_filter
from .utils import is_python_file
from ...nsn_logging import info, warning
from ...trie import FilePathTrie

DEFAULT_MODULE_FIELDS = set([
    '__builtins__', '__cached__', '__doc__', '__file__', '__loader__', '__name__', '__package__', '__spec__'
])


class SymbolType(Enum):
  TYPE = 0
  FUNCTION = 1
  ASSIGNMENT = 2
  MODULE = 3
  UNKNOWN = 4
  AMBIGUOUS = 5

  @staticmethod
  def from_pobject(pobject):
    try:
      value = pobject.value()
    except errors.AmbiguousFuzzyValueError:
      return SymbolType.AMBIGUOUS
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
    # type_ = type(obj)
    if isinstance(obj, types.ModuleType):
      return SymbolType.MODULE
    if isinstance(obj, (bool, str, int, float, type(None))):
      return SymbolType.ASSIGNMENT
    if isinstance(obj, (types.BuiltinMethodType, types.FunctionType, types.BuiltinFunctionType)):
      return SymbolType.FUNCTION
    if isinstance(obj, type):
      return SymbolType.TYPE

    return SymbolType.UNKNOWN


@attr.s(slots=True, hash=False)
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


@attr.s(slots=True, hash=False)
class _InternalSymbolEntry:
  '''This class stores information about module symbols in a format convenient for serialization.

  It generally should not be exposed through any public APIs outside of this file.
  '''
  symbol_type: SymbolType = attr.ib()
  module_key: module_loader.ModuleKey = attr.ib()
  # symbol_meta = attr.ib(None)
  not_yet_found_in_module = attr.ib(False)
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


@attr.s(slots=True, cmp=False, hash=False)
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
  # Indicates whether or not we track imports for files tracked by this index.
  is_import_tracking: bool = attr.ib(False, kw_only=True)
  _modified_since_save = attr.ib(False, kw_only=True)
  # This is introducing a circular dependency - to avoid subtle headaches with garbage collection
  #  breaking, we use weakrefs here.
  _symbol_index_weakref: weakref = attr.ib(kw_only=True)
  _file_history_tracker: FileHistoryTracker = attr.ib(None, kw_only=True)
  _location_index_trie = attr.ib(None, kw_only=True)
  _module_key_symbols_cache = attr.ib(factory=dict, kw_only=True)
  _module_keys_being_processed = attr.ib(factory=set, init=False)

  def __attrs_post_init__(self):
    if not os.path.exists(self.save_dir):
      os.makedirs(self.save_dir)

  def deep_equals(self, other):
    '''Compares this to another _LocationIndex in a deep manner. This is expensive.'''
    if self.save_dir != other.save_dir or self.location != other.location or self.is_import_tracking != other.is_import_tracking:
      return False
    if len(self.symbol_dict) != len(other.symbol_dict) or len(self.module_keys) != len(other.module_keys) or len(self.symbol_alias_dict) != len(other.symbol_alias_dict):
      return False
    for module_key in self.module_keys:
      if module_key not in other.module_keys:
        return False
    for symbol, subdict in self.symbol_dict.items():
      other_subdict = other.symbol_dict[symbol]
      if len(subdict) != len(other_subdict):
        return False
      for key, entry in subdict.items():
        other_entry = other_subdict[key]
        if entry != other_entry:
          return False
    for symbol, subdict in self.symbol_alias_dict.items():
      other_subdict = other.symbol_alias_dict[symbol]
      if len(subdict) != len(other_subdict):
        return False
      for key, entry in subdict.items():
        other_entry = other_subdict[key]
        if entry != other_entry:
          return False
    return True
  

  @staticmethod
  def create_builtins_index(save_dir):
    index = _LocationIndex(save_dir=save_dir,
                           location='builtins',
                           is_file_location=False,
                           symbol_index_weakref=lambda: None,
                           modified_since_save=True)
    # Add builtins to symbol_dict by default to account for all builtin symbols since most modules
    # aren't going to do a "from builtins import *" explicitly.
    builtins_module_key = module_loader.ModuleKey(module_loader.ModuleSourceType.BUILTIN, 'builtins')
    index._add_module_by_key(builtins_module_key)
    for symbol in utils.get_possible_builtin_symbols():
      if symbol not in index.symbol_dict:
        index.symbol_dict[symbol][(builtins_module_key,
                                   False)] = _InternalSymbolEntry(symbol_type=SymbolType.UNKNOWN,
                                                                  module_key=builtins_module_key)
    return index

  @staticmethod
  def create_location_index(save_dir, target_directory, is_import_tracking, symbol_index):
    file_history_tracker = FileHistoryTracker.load(os.path.join(save_dir, 'fht.msg'),
                                                   root_dir=target_directory,
                                                   filter_fn=python_package_filter)
    return _LocationIndex(save_dir=save_dir,
                          location=target_directory,
                          symbol_index_weakref=weakref.ref(symbol_index),
                          file_history_tracker=file_history_tracker,
                          is_import_tracking=is_import_tracking,
                          modified_since_save=True)

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

    return [
        self.location, d, alias_dict, serialized_module_key_list, self.is_file_location,
        self.is_import_tracking
    ]

  @staticmethod
  def _deserialize(unpacked, save_dir, symbol_index):
    location, d, alias_dict, serialized_module_key_list, is_file_location, is_import_tracking = unpacked
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
    return _LocationIndex(save_dir=save_dir,
                          location=location,
                          symbol_dict=symbol_dict,
                          symbol_alias_dict=symbol_alias_dict,
                          module_keys=set(module_key_list),
                          is_file_location=is_file_location,
                          is_import_tracking=is_import_tracking,
                          symbol_index_weakref=weakref.ref(symbol_index))

  def save(self):
    if not self._modified_since_save:
      return

    info(f'Saving updates for {self.location}')
    if not os.path.exists(self.save_dir):
      os.makedirs(self.save_dir)
    with open(os.path.join(self.save_dir, 'index.msg'), 'wb') as f:
      msgpack.pack(self._serialize(), f, use_bin_type=True)

    if self._file_history_tracker:
      self._file_history_tracker.save()
    self._modified_since_save = False

  @staticmethod
  def load(save_dir, symbol_index, readonly=False):
    filename = os.path.join(save_dir, 'index.msg')
    assert os.path.exists(filename)
    with open(filename, 'rb') as f:
      try:
        unpacked = msgpack.unpack(f, raw=False, use_list=not readonly)
      except msgpack.exceptions.UnpackException:
        warning(f'Unable to unpack {filename}')
        return None
      else:
        out = _LocationIndex._deserialize(unpacked, save_dir, symbol_index)
      # use_list=False is better for performance reasons - tuples faster and lighter, but tuples
      # cannot be appended to and thus make the SymbolIndex essentially readonly.
    out = _LocationIndex._deserialize(unpacked, save_dir, symbol_index)
    if out.is_file_location:
      out._file_history_tracker = FileHistoryTracker.load(os.path.join(save_dir, 'fht.msg'), out.location,
                                                          python_package_filter)
    else:
      out._file_history_tracker = None

    return out

  def _get_subtrie_index_pos(self):
    # The trie stored by location indicies is a subtrie of the main trie. It's start position is
    # not at then end of self.location necessarily because our trie utilizes remainders for
    # efficiency - so we have to account for that here.
    return len(self.location) - len(self._location_index_trie.remainder) + 1

  def update(self, directory):
    update_count = 0
    # Directory must be contained within this _LocationIndex or one of it's 'children'.
    assert self.is_file_location and len(directory) >= len(
        self.location) and directory[:len(self.location)] == self.location
    # Get any relevant child location indicies.
    subtree = self._location_index_trie.get_most_recent_ancestor_or_actual(
        directory[self._get_subtrie_index_pos():])
    children_location_indicies = [sv() for sv in subtree.children_store_value_iter()]
    for location_index in children_location_indicies:
      # These nodes are entirely contained, so update the whole thing.
      update_count += location_index.update(location_index.location)
    # Don't include child location indicies subdirs.
    if children_location_indicies:
      excluded_subdirs = set(location_index.location for location_index in children_location_indicies)
      filter_fn = lambda root, subdir: os.path.join(
          root, subdir) not in excluded_subdirs and python_package_filter(root, subdir)
    else:
      filter_fn = python_package_filter
    update_and_filenames = self._file_history_tracker.get_files_in_dir_modified_since_timestamp(
        self.location, auto_update=True)
    for update, filename in update_and_filenames:
      update_count += 1
      if update:
        self.add_file(filename, check_timestamp=False)
      else:
        self.remove_file(filename)
    self.save()
    return update_count

  def add_path(self, path=False):
    '''Adds python files under |path| to this index.

    This will only add python packages (i.e. directories with __init__.py) beneath |path|, however,
    even if |path| is itself not a python package, all python files directly in it will still
    be added. This essentially mirror behavior with sys.path in pythons module finding logic.'''

    assert os.path.exists(path)
    assert self.location == path[:len(self.location)]

    if not os.path.isdir(path):
      self.add_file(path)
      return 1

    # Always add to the location index that is closest to the path.
    check_descendent_index = self._location_index_trie and self._location_index_trie.has_children()
    if check_descendent_index:
      location_index = self._location_index_trie.get_most_recent_ancestor_or_actual(path).store_value()
      if id(location_index) != id(self):
        return location_index.add_path(path)

    location_indicies = [self] + list(
        self._location_index_trie.children_store_value_iter()) if check_descendent_index else [self]

    add_count = 0
    for location_index in location_indicies:
      # Note: this will naturally filter out non-python packages by chekcing for __init__.py in
      # subdirs. It will *not* check for __init__.py directly under |path|.
      update_and_full_filenames = location_index._file_history_tracker.get_files_in_dir_modified_since_timestamp(
          path, auto_update=True)
      for update, full_filename in update_and_full_filenames:
        if update and is_python_file(full_filename):
          self.add_file(full_filename, check_descendent_index=check_descendent_index)
          add_count += 1
    self.save()
    return add_count

  def add_file(self, filename, *, check_descendent_index=True, check_timestamp=True):
    if not is_python_file(filename):
      return

    if check_timestamp and not self._file_history_tracker.has_file_changed_since_timestamp(filename):
      return

    module_key = module_loader.ModuleKey.from_filename(filename)
    self._add_module_by_key(module_key,
                            check_descendent_index=check_descendent_index,
                            check_timestamp=check_timestamp)
    self._file_history_tracker.update_timestamp_for_path(filename)
    self._modified_since_save = True  # File history changed if nothing else.

  def remove_file(self, filename):
    symbol_index = self._symbol_index_weakref()
    if not symbol_index:
      return
    # TODO: Merge better with _add_module_by_key.
    module_key = module_loader.ModuleKey.from_filename(filename)
    if module_key not in self._module_key_symbols_cache:
      warning(f'Scanning symbol_dict for lone key :/.')
      self._add_module_keys_symbols_to_cache([module_key])
    existing_symbols = self._module_key_symbols_cache[module_key]
    for name in existing_symbols.keys():
      del self.symbol_dict[name][(module_key, False)]
    del self.symbol_dict[module_key.get_basename()][(module_key, True)]
    # TODO: Merge better with _process_tracked_imports.
    existing_module_key_to_value_as_name_dict = self._load_existing_module_value_as_names(module_key)
    if existing_module_key_to_value_as_name_dict:
      for module_key, existing_value_as_name_set in existing_module_key_to_value_as_name_dict.items():
        location_index = symbol_index._get_location_index_for_module_key(module_key)
        # Remove any symbol references that are no longer present in the file.
        for value, as_name in existing_value_as_name_set:
          _update_symbol(location_index.module_keys,
                         location_index.symbol_dict,
                         location_index.symbol_alias_dict,
                         module_key=module_key,
                         value=value,
                         as_name=as_name,
                         count_delta=-1)
    self._modified_since_save = True

  def _add_module_by_key(self, module_key, check_descendent_index=True, check_timestamp=True):
    symbol_index = self._symbol_index_weakref()
    if not symbol_index:
      return
    if module_key in symbol_index._failed_module_keys:
      return
    if check_descendent_index and self._location_index_trie and self._location_index_trie.has_children():
      # We key on non-stub filenames
      filename = module_key.get_filename(prefer_stub=False)
      assert self.location == filename[:len(self.location)]
      # This will get the exact correct trie, regardless of how deep. store_value is a weakref.
      trie = self._location_index_trie.get_most_recent_ancestor_or_actual(
          filename[self._get_subtrie_index_pos():], filter_fn=trie_has_location_index)
      location_index = trie.store_value()
      return location_index._add_module_by_key(module_key, check_descendent_index=False)

    # Avoid recursion problems by nipping them in the bud here.
    if module_key in self._module_keys_being_processed:
      return
    self._module_keys_being_processed.add(module_key)
    try:
      module_key_already_present = module_key in self.module_keys
      # Don't add bad modules or re-add builtins.
      if module_key.is_bad() or (not module_key.is_loadable_by_file() and module_key_already_present):
        return False

      if check_timestamp and module_key.is_loadable_by_file(
      ) and not self._file_history_tracker.has_file_changed_since_timestamp(
          module_key.get_filename(prefer_stub=False)):
        return False

      # # Note that we explicity do this here instead of in _add_module_by_key as the latter may have
      # # already been done without tracking the module's contents and would thus return early.
      # module = None

      # TODO: Do a proper 'reload' - which means loading all dependent modules as well whose values
      # may change as a result...
      if module_key_already_present:
        # Delete module so that we get the new module from scratch.
        module_loader.remove_module_by_key(module_key)

      # module = module if module else module_loader.get_module_from_key(
      #     module_key, lazy=False, include_graph=False, force_real=True)
      if module_key_already_present:
        info(f'{module_key} already recorded - getting symbols.')
        # TODO: This list could be created more efficiently at loading time if done carefully - i.e.
        # check which files are going to need updating from FHT, then save the symbols for those files
        # when creating symbol_dict.
        if module_key not in self._module_key_symbols_cache:
          warning(f'Scanning symbol_dict for lone key :/.')
          self._add_module_keys_symbols_to_cache([module_key])
        existing_symbols = self._module_key_symbols_cache[module_key]
        del self._module_key_symbols_cache[module_key]  # About to invalidate.
      else:
        existing_symbols = {}

      python_module = module_loader.get_python_module_from_module_key(module_key,
                                                                      force_reload=True)
      if not python_module:
        symbol_index._failed_module_keys.add(module_key)
        return

      if module_key.module_source_type == module_loader.ModuleSourceType.NORMAL:
        graph = module_loader.load_graph_from_module_key(module_key)
        global_imports = graph.get_global_imported_symbols()
        if self.is_import_tracking:
          directory = os.path.dirname(module_key.get_filename(False))
          self._process_tracked_imports(module_key, graph, directory)

      else:
        global_imports = set()
      for name in filter(lambda x: x not in DEFAULT_MODULE_FIELDS, dir(python_module)):
        member = getattr(python_module, name)
        imported = name in global_imports
        if name in existing_symbols:
          entry = existing_symbols[name]
          # Update attributes as needed.
          # TODO: Clean up this logic so we're not messing around with _modified_since_save so much.
          # Perhaps properties + dirty bit? Or perhaps just assume modified if we're in this func
          # at all?
          symbol_type = SymbolType.from_real_obj(member)
          if symbol_type != entry.symbol_type:
            entry.symbol_type = symbol_type
            self._modified_since_save = True

          if entry.not_yet_found_in_module:
            entry.not_yet_found_in_module = True
            self._modified_since_save = True

          # save graphs in module_loader, sep from module
          # get imported symbols from graph - cross check here.

          # This is an approximation to determine if a value is imported - it's guestimated to be
          # reasonably accurate, but will miss some imported cases (e.g. import a; b = a) and catch
          # others (e.g. imported symbols that are subsequently replaced).

          if entry.imported != imported:
            entry.symbol_type = symbol_type
            self._modified_since_save = True
          del existing_symbols[name]
        else:
          entry = _get_or_add_entry(module_keys=self.module_keys,
                                    symbol_dict=self.symbol_dict,
                                    module_key=module_key,
                                    is_module_itself=False,
                                    real_name=name)
          entry.symbol_type = SymbolType.from_real_obj(member)
          entry.not_yet_found_in_module = False
          entry.is_module_itself = False
          entry.imported = imported

      # Remove any remaining existing symbols that have since been removed.
      for name in existing_symbols.keys():
        d = self.symbol_dict[name]
        entry = d[(module_key, False)]
        if entry.import_count > 0:
          # Some tracked things are still importing this it seems - just mark it as no longer found.
          entry.not_yet_found_in_module = True
        else:  # Safe to delete.
          del d[(module_key, False)]

      if not module_key_already_present:
        self._modified_since_save = True
        self.module_keys.add(module_key)
        entry = _get_or_add_entry(module_keys=self.module_keys,
                                  symbol_dict=self.symbol_dict,
                                  module_key=module_key,
                                  is_module_itself=True,
                                  real_name=module_key.get_basename())
        entry.symbol_type = SymbolType.MODULE
        entry.not_yet_found_in_module = False
        entry.is_module_itself = True
        entry.imported = False

      if module_key.is_loadable_by_file():
        self._modified_since_save = True
        self._file_history_tracker.update_timestamp_for_path(module_key.get_filename(prefer_stub=False))

      if self.is_import_tracking:
        module_loader.keep_graphs_default = False
      info(f'module_key loaded: {module_key}')
    finally:
      self._module_keys_being_processed.remove(module_key)
    return not module_key_already_present

  def _add_module_keys_symbols_to_cache(self, module_keys):
    cache = self._module_key_symbols_cache
    keys = [(module_key, False) for module_key in module_keys]
    for module_key in module_keys:
      cache[module_key] = {}
    for symbol, subdict in self.symbol_dict.items():
      for key in keys:
        if key in subdict:
          cache[key[0]][symbol] = subdict[key]

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
      module_keys = location_index.module_keys
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
        _update_symbol(module_keys, symbol_dict, symbol_alias_dict, module_key, value, as_name, 1)
      # Remove any symbol references that are no longer present in the file.
      for value, as_name in existing_value_as_name_set:
        _update_symbol(module_keys, symbol_dict, symbol_alias_dict, module_key, value, as_name, -1)
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
      return defaultdict(set, {module_loader.ModuleKey.deserialize(k): set(v) for k, v in d.items()})

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


def _get_or_add_entry(module_keys, symbol_dict, module_key, is_module_itself, real_name):
  key = (module_key, is_module_itself)
  key_dict = symbol_dict[real_name]
  if key in key_dict:
    return key_dict[key]
  # Dynamically create and track.
  entry = key_dict[key] = _InternalSymbolEntry(SymbolType.UNKNOWN,
                                               module_key,
                                               not_yet_found_in_module=True,
                                               imported=False)
  module_keys.add(module_key)
  # Add to cache
  # self._module_key_symbols_cache[module_key][real_name] = entry
  return entry


def _update_symbol(module_keys, symbol_dict, symbol_alias_dict, module_key, value, as_name, count_delta):
  real_name = value if value else module_key.get_basename()
  is_module_itself = False if value else True
  entry = _get_or_add_entry(module_keys, symbol_dict, module_key, is_module_itself, real_name)
  entry.import_count += count_delta
  # Check if entry only was present due to imports and is no longer imported by anyone. If it is
  # no longer reference and not found directly from a module, we should delete it.
  if entry.import_count <= 0 and entry.not_yet_found_in_module:
    del symbol_dict[real_name][(module_key, is_module_itself)]
  if as_name:
    symbol_alias_count_dict = symbol_alias_dict[as_name]
    args = (real_name, module_key, is_module_itself)
    if args in symbol_alias_count_dict:
      alias = symbol_alias_count_dict[args]
      alias.import_count += count_delta
      if alias.import_count <= 0:  # Alias no longer used anywhere.
        del symbol_alias_count_dict[args]
    else:
      assert count_delta > 0
      symbol_alias_count_dict[args] = _SymbolAlias(*args, import_count=count_delta)


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
        module_key = module_loader.module_key_from_name(
            module_loader.join_module_attribute(node.module_path, value), source_dir)
        if module_key.module_source_type != module_loader.ModuleSourceType.BAD:
          value = None
        else:
          module_key = None
      if not module_key:
        module_key = module_loader.module_key_from_name(node.module_path, source_dir)
      if module_key.module_source_type != module_loader.ModuleSourceType.BAD:
        imported_module_key_to_value_as_names[module_key].append((value, as_name))
  return imported_module_key_to_value_as_names


@attr.s(slots=True)
class SymbolIndex:
  save_dir = attr.ib()
  _builtins_location_index = attr.ib()
  _location_indicies = attr.ib(factory=list)
  # This just mirrors the list above (minus builtin), but is more efficient for certain operations.
  _file_location_indicies_trie = attr.ib(factory=FilePathTrie)
  _module_key_to_location_index_dict = attr.ib(factory=dict)
  _failed_module_keys = attr.ib(factory=set)

  def deep_equals(self, other):
    '''Performs a deep check to determine if |other| matches this SymbolIndex. This is expensive.'''
    if self.save_dir != other.save_dir:
      assert False
    if len(self._location_indicies) != len(other._location_indicies):
      assert False
    for location_index in self._location_indicies:
      if not location_index.is_file_location:
        continue  # skip builtins.
      trie = other._file_location_indicies_trie.get_node(location_index.location)
      if not trie:
        assert False
      other_location_index = trie.store_value()
      if not other_location_index.deep_equals(location_index):
        assert False
    if len(self._failed_module_keys) != len(other._failed_module_keys):
      assert False
    for module_key in self._failed_module_keys:
      if module_key not in other._failed_module_keys:
        assert False
    return True

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

    failed_path = os.path.join(save_dir, 'failed.msg')
    if os.path.exists(failed_path):
      with open(failed_path, 'rb') as f:
        # use_list=False is better for performance reasons - tuples faster and lighter, but tuples
        # cannot be appended to and thus make the SymbolIndex essentially readonly.
        failed_module_keys = SymbolIndex._deserialize(msgpack.unpack(f, raw=False, use_list=not readonly))
    else:
      failed_module_keys = set()

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
        if not location_index:
          warning(f'Failed to load LocationIndex from {full_filename}. Deleting corrupted dir.')
          shutil.rmtree(full_filename)
          continue
        location_indicies.append(location_index)
        if not location_index.is_file_location:
          index._builtins_location_index = location_index
        for mk in location_index.module_keys:
          module_key_to_location_index_dict[mk] = location_index

    trie = index._file_location_indicies_trie
    # Note: order doesn't matter since returned FilePathTries are stable.
    for location_index in filter(lambda x: x.is_file_location, location_indicies):
      location_index._location_index_trie = trie.add(location_index.location,
                                                     value=0,
                                                     store_value=weakref.ref(location_index))

    index._file_location_indicies_trie = trie

    # save_dir may be only partially completed if someone messed with the dir or things crashed
    # somewhere. Just in case, check things out.
    index._fill_in_missing()
    return index

  # TODO:
  # @staticmethod
  # def build_complete_index(save_dir):
  #   index = SymbolIndex.create_index(save_dir)
  #   for path in sys.path:
  #     index.add_path(path, ignore_init=True)

  #   return index

  @staticmethod
  def create_index(save_dir, sys_path=sys.path):
    assert not os.path.exists(save_dir)
    os.makedirs(save_dir)

    index = SymbolIndex(save_dir, None)
    index._fill_in_missing(sys_path)
    return index

  def _fill_in_missing(self, sys_path=sys.path):
    if not self._builtins_location_index:
      self._builtins_location_index = _LocationIndex.create_builtins_index(
          SymbolIndex._get_location_save_dir_from_main_dir(self.save_dir, 'builtins'))
      self._location_indicies.append(self._builtins_location_index)

    for path in sys_path:
      if not path:
        continue
      self._get_or_add_location_index_for_dir(os.path.abspath(path))

  @staticmethod
  def build_index_from_package(package_path, save_dir, clean=False, sys_path=sys.path):
    package_path = os.path.abspath(package_path)
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
      index = SymbolIndex.create_index(save_dir, sys_path=sys_path)
    # Ensure path is included in an index.
    index._get_or_add_location_index_for_dir(package_path, True)
    index.add_path(package_path, is_import_tracking=True)
    index.save()
    return index

  @staticmethod
  def _get_location_save_dir_from_main_dir(save_dir, location_name):
    return os.path.join(save_dir, str(hash(location_name)))

  def _get_location_save_dir(self, location_name):
    return SymbolIndex._get_location_save_dir_from_main_dir(self.save_dir, str(hash(location_name)))

  def _get_or_add_location_index_for_dir(self, directory, is_import_tracking=False):
    if not os.path.exists(directory):
      return
    directory = os.path.abspath(directory)
    location_index = self._get_location_index_for_filename(directory)
    # TODO: If a _LocationIndex exists already w/o is_import_tracking and we want it, we need to do
    # a bunch of work to go track everything. Also, might need to split out. DF"KDSOIFJDS. Too tired.
    if is_import_tracking and location_index and not location_index.is_import_tracking:
      if location_index.location != directory:
        assert not location_index.module_keys
        return self._create_location_index(directory, is_import_tracking)
      else:
        assert not location_index.module_keys  # Ensure we've not already added shit.
        location_index.is_import_tracking = True

    if location_index:
      # TODO: Support splitting _LocationIndicies beneath a higher-level directory. E.g. /a -> /a/b.
      assert location_index.location in directory
      return location_index

    # Doesn't exist - create.
    return self._create_location_index(directory, is_import_tracking)

  def _create_location_index(self, directory, is_import_tracking):
    location_index = _LocationIndex.create_location_index(self._get_location_save_dir(directory), directory,
                                                          is_import_tracking, self)
    self._location_indicies.append(location_index)
    # Note: Rather neatly, if this new directory is above some existing directories, the FilePathTrie will
    # allow things to work as-expected - that is, this location index shall not track those subdirs
    # because when adding paths, it will check the trie for appropriate children.
    trie = self._file_location_indicies_trie.add(directory, value=0, store_value=weakref.ref(location_index))
    location_index._location_index_trie = trie
    return location_index

  def _get_location_index_for_module_key(self, module_key):
    if module_key in self._module_key_to_location_index_dict:
      return self._module_key_to_location_index_dict[module_key]

    if module_key.is_bad():
      return None

    if module_key.module_source_type == module_loader.ModuleSourceType.BUILTIN:
      return self._builtins_location_index

    filename = module_key.get_filename(prefer_stub=False)
    location_index = self._get_location_index_for_filename(filename)
    if not location_index:
      # Darn, need to create.
      info(f'Creating LocationIndex for dir of {filename}')
      location_index = self._get_or_add_location_index_for_dir(os.path.dirname(filename))
    assert location_index and location_index.location in filename
    self._module_key_to_location_index_dict[module_key] = location_index
    return location_index

  def _get_location_index_for_filename(self, filename):
    filename = os.path.abspath(filename)
    trie = self._file_location_indicies_trie.get_most_recent_ancestor_or_actual(
        filename, filter_fn=trie_has_location_index)
    if trie:
      return trie.store_value()
    return None

  def update(self, directory, is_import_tracking):
    directory = os.path.abspath(directory)
    # If dir is lower than multiple indicies, multiple indicies may be associated with it.
    # location_indicies = self._get_location_indicies_for_dir(directory)
    trie = self._file_location_indicies_trie.get_most_recent_ancestor_or_actual(
        directory, filter_fn=trie_has_location_index)
    if not trie:
      info(f'Adding {directory} to index!')
      return self.add_path(directory, is_import_tracking=is_import_tracking)
    assert trie, "Directory not captured in index yet."
    location_index = trie.store_value()
    return location_index.update(directory)

  def add_path(self, path, is_import_tracking=False):
    path = os.path.abspath(path)
    assert os.path.exists(path)
    if not os.path.isdir(path):
      self.add_file(path)
      return 1

    location_index = self._get_or_add_location_index_for_dir(path, is_import_tracking)

    return location_index.add_path(path)

  def add_file(self, filename):
    filename = os.path.abspath(filename)
    module_key = module_loader.ModuleKey.from_filename(filename)
    self._add_module_by_key(module_key)

  def _add_module_by_key(self, module_key):
    if module_key.is_bad():
      self._failed_module_keys.append(module_key)
      return
    location_index = self._get_location_index_for_module_key(module_key)
    if not location_index:
      assert module_key.is_loadable_by_file()
      # Dynamically create a _LocationIndex for the directory containing the module.
      location_index = self._get_or_add_location_index_for_dir(
          os.path.dirname(module_key.get_filename(prefer_stub=False)))
    assert location_index
    assert not module_key.is_loadable_by_file() or (location_index.location in module_key.get_filename(False))
    newly_added = location_index._add_module_by_key(module_key)
    if newly_added:
      self._module_key_to_location_index_dict[module_key] = location_index
    return location_index


def trie_has_location_index(trie):
  # store_value is a weakref to a LocationIndex or None.
  return trie.store_value and trie.store_value()


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
