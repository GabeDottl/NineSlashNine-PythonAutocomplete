import builtins
import os
import sys
import types
from collections import OrderedDict, defaultdict
from enum import Enum
from functools import partial
from glob import glob
from typing import Dict, Tuple

import attr
import msgpack
from autocomplete.code_understanding.typing import (control_flow_graph_nodes, errors, language_objects,
                                                    module_loader, utils)
from autocomplete.nsn_logging import info, warning


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


@attr.s
class SymbolEntry:
  symbol_type: SymbolType = attr.ib()
  module_type: 'ModuleType' = attr.ib()
  module_index: int = attr.ib()
  symbol_meta = attr.ib(None)
  is_module_itself: bool = attr.ib(False)
  imported : bool= attr.ib(False)
  import_count: int = attr.ib(0)
  real_name: str = attr.ib(None)  # Only used if the entry is an alias.

  def serialize(self):
    args = list(attr.astuple(self))
    args[0] = args[0].value  # symbol_type
    args[1] = args[1].value  # module_type
    return args

  @staticmethod
  def deserialize(tuple_):
    args = list(tuple_)
    args[0] = SymbolType(args[0])  # symbol_type
    args[1] = language_objects.ModuleType(args[1])  # module_type
    # if tuple_[1] is not None:
    #   return SymbolEntry(SymbolType(tuple_[0]), language_objects.ModuleType(tuple_[1]), *tuple_[2:])
    return SymbolEntry(*args)
    # return SymbolEntry(SymbolType(tuple_[0]), *tuple_[1:])

  def is_from_native_module(self):
    return self.module_type == language_objects.ModuleType.BUILTIN


@attr.s
class SymbolIndex:
  symbol_dict = attr.ib(factory=partial(defaultdict, dict))
  # Bi-directional dict.
  module_list: List[module_loader.ModuleKey] = attr.ib(factory=list)
  module_dict: Dict[module_loader.ModuleKey, int]  = attr.ib(factory=dict)

  failed_files = attr.ib(factory=set)
  files_added = attr.ib(0, init=False)
  path = attr.ib(None, init=False)
  # Key is: (from_import, module_name, module_filename)
  value_module_reference_map: Dict[Tuple[str, str, str], int] = attr.ib(
      factory=partial(defaultdict, int), init=False)

  def get_native_module_name_from_symbol_entry(self, symbol_entry):
    return self.module_list[symbol_entry.module_index]

  def __attrs_post_init__(self):
    if not len(self.symbol_dict):
      # Add builtins to symbol_dict by default if it's not been initialized with some set.
      for symbol, value in builtins.__dict__.items():

        self.symbol_dict[symbol][(-1, False)] = SymbolEntry(SymbolType.from_real_obj(value), language_objects.ModuleType.BUILTIN, -1)
      for symbol in utils.get_possible_builtin_symbols():
        if symbol not in self.symbol_dict:
          self.symbol_dict[symbol][(-2, False)] =            SymbolEntry(SymbolType.UNKNOWN, language_objects.ModuleType.BUILTIN, -2)
    if len(self.module_list) != len(self.module_dict):
      self.module_dict = {x: i for i, x in enumerate(self.module_list)}

  def find_symbol(self, symbol):
    if symbol not in self.symbol_dict:
      return []
    return self.symbol_dict[symbol].values()

  def get_modules_for_symbol_entries(self, symbol_entries):
    for symbol_entry in symbol_entries:
      # if symbol_entry.module_type.is_native():
      #   yield symbol_entry, self.module_list[symbol_entry.module_index]
      # else:
      yield symbol_entry, self.module_list[symbol_entry.module_index]

  @staticmethod
  def _serialize(index):
    d = {}
    symbol_entries = []
    symbol_entries_dict = {}
    for symbol, module_index_symbol_entry_dict in index.symbol_dict.items():
      d[symbol] = [v.serialize() for v in module_index_symbol_entry_dict.values()]
    # module_list = index.module_list if index.module_list else [0]
    # module_list = index.module_list if index.module_list else [0]
    serialized_module_list = [key.module_source_type.value, key.path for key in index.module_list]
    return [d, serialized_module_list, tuple(index.failed_files)]

  @staticmethod
  def _deserialize(unpacked):
    d, symbol_entries, serialized_module_list, failed_files_list = unpacked
    module_list = [module_loader.ModuleKey(module_loader.ModuleSourceType(type_), path) for type_, path in serialized_module_list]
    symbol_dict = {}
    for s, serialized_symbol_entries in d.items():
      module_index_symbol_entry_dict = {}
      for serialized_entry in serialized_symbol_entries:
        # TODO: Need to match this!!!!!!
        symbol_entry = SymbolEntry.deserialize(serialized_entry)
        module_index_symbol_entry_dict[(symbol_entry.module_index, symbol_entry.is_module_itself)] = symbol_entry
      symbol_dict[s]= module_index_symbol_entry_dict

    module_dict = {x: i for i, x in enumerate(module_list)}
    return SymbolIndex(symbol_dict, module_list=module_list, module_dict=module_dict, failed_files=set(failed_files_list))

  @staticmethod
  def load(filename, readonly=False):
    with open(filename, 'rb') as f:
      # use_list=False is better for performance reasons - tuples faster and lighter, but tuples
      # cannot be appended to and thus make the SymbolIndex essentially readonly.
      out = SymbolIndex._deserialize(msgpack.unpack(f, raw=False, use_list=not readonly))
    out.path = filename
    return out

  def save(self, filename):
    with open(filename, 'wb') as f:
      msgpack.pack(self, f, default=SymbolIndex._serialize, use_bin_type=True)

  @staticmethod
  def build_index(target_index_filename):
    index = SymbolIndex()
    index.path = target_index_filename
    for path in sys.path:
      index.add_path(path, ignore_init=True)
    return index

  @staticmethod
  def build_index_from_package(package_path, target_index_filename):
    assert os.path.exists(package_path)
    index = SymbolIndex()
    index.path = target_index_filename
    index.add_path(package_path, ignore_init=True, track_imported_modules=True)

    for (value, as_name, module_key), count in index.value_module_reference_map.items():
      index.add_module_by_key(module_key)

      if value:
        module_index_symbol_entry_dict = index.symbol_dict[value]
      else:
        symbol = module_name[module_name.rfind('.') + 1:]
        module_index_symbol_entry_dict = index.symbol_dict[symbol]

      is_module_itself = not value
      module_index = self.module_dict[module_key]
      
      key = (module_index, is_module_itself)
      assert key in module_index_symbol_entry_dict:
      entry = module_index_symbol_entry_dict[key]
      entry.import_count += 1

      if as_name:
        module_index_symbol_entry_dict = index.symbol_dict[as_name]
        if key in module_index_symbol_entry_dict:
          # Already have alias recorded.
          continue
        else:
          index.symbol_dict[as_name][key] = entry
      # TODO: Hash on module_index?
      for entry in module_index_symbol_entry_dict:
        if entry.module_index == module_index and ((not value and entry.is_module_itself) or
                                                   (value and not entry.is_module_itself)):
          if as_name:
              # if as_name in index.symbol_dict:
            real_name = value if value else base_module_name(module_name)

            if value:
              if module_filename:
                module = module_loader.get_module_from_filename(module_name, module_filename)
              else:
                module = module_loader.get_module(module_name, directory=None)
              symbol_type = SymbolType.from_pobject_value(module[value])
            else:
              symbol_type = SymbolType.MODULE
          entry.import_count += count
          break
    return index

  
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
    import_nodes = graph.get_descendents_of_types((control_flow_graph_nodes.ImportCfgNode,
                                                   control_flow_graph_nodes.FromImportCfgNode))
    imported_symbols_and_modules = []
    for node in import_nodes:
      if isinstance(node, control_flow_graph_nodes.ImportCfgNode):
        values = [(None, node.as_name)]
      else:
        values = node.from_import_name_alias_dict.items()
      for value, as_name in values:
        imported_filename = ''
        module_name = node.module_path
        if value:
          imported_filename, _, _ = module_loader.get_module_info_from_name(f'{node.module_path}.{value}',
                                                                      directory)[0]
          # If the from import is importing a module itself, then put it in the module_name
          if imported_filename:
            module_name = f'{module_name}.{value}'
            value = None
        if not imported_filename:
          imported_filename = module_loader.get_module_info_from_name(module_name, directory)[0]
        imported_symbols_and_modules.append((value, as_name, module_name, imported_filename))
    for value_as_name_module_name_filename in imported_symbols_and_modules:
      self.value_module_reference_map[value_as_name_module_name_filename] += 1

  def add_file(self, filename, track_imported_modules=False):
    try:
      module_key = module_loader.ModuleKey.from_filename(filename)
    except ValueError:
      return
    return self.add_module_by_key(module_key, track_imported_modules)
    
  def add_module_by_key(self, module_key, track_imported_modules=False)
    filename = module_key.path if module_key.module_source_type != module_loader.ModuleSourceType.BUILTIN else None
    if module_key in self.module_dict or filename in self.failed_files:
      warning(f'Skipping {filename} - already processed.')
      return

    info(f'Adding to index: {module_key}')
    module_index = len(self.module_list)
    try:
      if track_imported_modules:
        module = module_loader.get_module_from_filename('__main__', filename, lazy=False, include_graph=True)
        directory = os.path.dirname(filename)
        self._track_modules(module.graph, directory)
      else:
        module = module_loader.get_module_from_filename(
            '__main__', filename, unknown_fallback=True, lazy=False, include_graph=False)
      if module.module_type == language_objects.ModuleType.UNKNOWN_OR_UNREADABLE:
        info(f'Failed on {filename} - unreadable')
        self.failed_files.add(filename)
        return

      self.add_module(module, module_index)
    except OSError as e:  # Exception
      info(f'Failed on {filename}: {e}')
      self.failed_files.add(filename)
    else:
      self.files_added += 1
      self.module_dict[module_key] = module_index
      self.module_list.append(module_key)
      self.symbol_dict[module_key.to_module_basename()][(module_index, True)] = 
          SymbolEntry(SymbolType.MODULE, module.module_type, module_index, is_module_itself=True)
      if self.files_added and self.files_added % 20 == 0 and self.path:
        info(f'Saving index to {self.path}. {self.files_added} files added.')
        self.save(self.path)
        # self.files_added = 0

  # def add_module_by_name(self, module_name, filename):
  #   if filename and filename in self.module_dict:
  #     return  # Already added.

  #   if not filename:
  #     if module_name in self.module_dict:
  #       return  # Already loaded.

  #   if filename and os.path.exists(filename):
  #     self.add_file(filename)
  #   else:
  #     module = module_loader.get_module(module_name, '', lazy=False)
  #     index = len(self.module_list)
  #     self.add_module(module, index)

  #     self.symbol_dict[module_key.to_module_basename()].append(
  #         SymbolEntry(SymbolType.MODULE, module.module_type, module_index, is_module_itself=True))
  #     self.module_dict[module_name] = index
  #     self.module_list.append(module_name)


  def add_module(self, module, module_index):
    # filename = module.filename
    for name, member in filter(lambda kv: _should_export_symbol(module, *kv), module.items()):
      try:
        self.symbol_dict[name][(module_index, False)] = 
            SymbolEntry(
                SymbolType.from_pobject_value(member.value()),
                module.module_type,
                module_index,
                imported=member.imported)
      except errors.AmbiguousFuzzyValueError:
        self.symbol_dict[name][(module_index, False)] = 
            SymbolEntry(SymbolType.AMBIGUOUS, module.module_type, module_index, imported=member.imported)
    # if module.filename:
    #   module_basename = os.path.splitext(os.path.basename(module.filename))[0]
    #   if module_basename == '__init__':
    #     module_basename = os.path.basename(os.path.dirname(module.filename))
    #   self.symbol_dict[module_basename].append(
    #       SymbolEntry(SymbolType.MODULE, module.module_type, module_index, is_module_itself=True))
    # else:  # Native.
    #   self.symbol_dict[module_key.to_module_basename()].append(
    #       SymbolEntry(SymbolType.MODULE, module.module_type, module_index, is_module_itself=True))
    

def get_imported_modules(graph, directory):
  import_nodes = graph.get_descendents_of_types((control_flow_graph_nodes.ImportCfgNode,
                                                 control_flow_graph_nodes.FromImportCfgNode))
  return set([(node.module_path, module_loader.get_module_info_from_name(node.module_path, directory)[0])
              for node in import_nodes])


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
  index.save(output_path)


if __name__ == "__main__":
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('target_package')
  parser.add_argument('output_path')
  args = parser.parse_args()
  main(args.target_package, args.output_path)
