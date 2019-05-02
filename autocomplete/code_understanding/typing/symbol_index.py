import os
import sys
import types
from collections import defaultdict, OrderedDict
from enum import Enum
from functools import partial
from glob import glob

import attr
import msgpack

from autocomplete.code_understanding.typing import (errors, language_objects, module_loader, utils)
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
    if isinstance(value, language_objects.Instance):
      return SymbolType.ASSIGNMENT
    if isinstance(value, language_objects.Klass):
      return SymbolType.TYPE
    if isinstance(value, language_objects.Function):
      return SymbolType.FUNCTION
    return SymbolType.UNKNOWN

  @staticmethod
  def from_real_obj(obj):
    type_ = type(obj)
    if isinstance(type_, type):
      return SymbolType.TYPE
    if isinstance(type_, (types.BuiltinMethodType, types.FunctionType, types.BuiltinFunctionType)):
      return SymbolType.FUNCTION
    if isinstance(type_, (bool, str, int, float, type(None), type)):
      return SymbolType.ASSIGNMENT
    return SymbolType.UNKNOWN


@attr.s
class SymbolEntry:
  symbol_type: SymbolType = attr.ib()
  module_type: 'ModuleType' = attr.ib()
  module_key: int = attr.ib()
  symbol_meta = attr.ib(None)

  def serialize(self):
    if self.module_type:
      return (self.symbol_type.value, self.module_type.value, self.module_key)
    return (self.symbol_type.value, None, 0)

  @staticmethod
  def deserialize(tuple_):
    if tuple_[1] is not None:
      return SymbolEntry(SymbolType(tuple_[0]), language_objects.ModuleType(tuple_[1]), *tuple_[2:])
    return SymbolEntry(SymbolType(tuple_[0]), *tuple_[1:])


@attr.s
class SymbolIndex:
  symbol_dict = attr.ib(factory=partial(defaultdict, list))
  native_module_list = attr.ib(factory=OrderedDict)
  normal_module_list = attr.ib(factory=OrderedDict)
  failed_files = attr.ib(factory=set)
  files_added = attr.ib(0, init=False)
  path = attr.ib(None, init=False)

  def __attrs_post_init__(self):
    if not len(self.symbol_dict):
      # Add builtins to symbol_dict by default if it's not been initialized with some set.
      for symbol, value in __builtins__.items():
        self.symbol_dict[symbol].append(SymbolEntry(SymbolType.from_real_obj(value), None, 0))
      for symbol in utils.get_possible_builtin_symbols():
        if symbol not in self.symbol_dict:
          self.symbol_dict[symbol].append(SymbolEntry(SymbolType.UNKNOWN, None, 0))

  def find_symbol(self, symbol):
    return self.symbol_dict[symbol]

  @staticmethod
  def _serialize(index):
    d = {}
    for symbol, values in index.symbol_dict.items():
      d[symbol] = [v.serialize() for v in values]
    # native_module_list = index.native_module_list if index.native_module_list else [0]
    # normal_module_list = index.normal_module_list if index.normal_module_list else [0]
    return [d, index.native_module_list, index.normal_module_list, tuple(index.failed_files)]

  @staticmethod
  def _deserialize(unpacked):
    d, native_module_list, normal_module_list, failed_files = unpacked
    symbol_dict = {s: [SymbolEntry.deserialize(v) for v in values] for s, values in d.items()}
    return SymbolIndex(symbol_dict, native_module_list, normal_module_list, set(failed_files))

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

  def add_path(self, path, ignore_init=False, include_private_files=False):
    if not os.path.exists(path):
      return
    init_file = os.path.join(path, '__init__.py')
    if ignore_init or os.path.exists(init_file):
      info(f'Adding dir: {path}')
      for filename in glob(os.path.join(path, '*.py')):
        self.add_file(filename)
      for directory in filter(lambda p: os.path.isdir(os.path.join(path, p)), os.listdir(path)):
        self.add_path(os.path.join(path, directory))

  def add_file(self, filename):
    if filename in self.normal_module_list or filename in self.failed_files:
      warning(f'Skipping {filename} - already processed.')
      return

    info(f'Adding to index: {filename}')
    file_index = len(self.normal_module_list)
    try:
      module = module_loader.get_module_from_filename('__main__', filename, lazy=False)
      self.add_module(module, file_index)
    except OSError:  #Exception as e:
      info(f'Failed on {filename}: {e}')
      self.failed_files.add(filename)
    else:
      self.files_added += 1
      self.normal_module_list[filename] = file_index
      if self.files_added and self.files_added % 20 == 0 and self.path:
        info(f'Saving index to {self.path}. {self.files_added} files added.')
        self.save(self.path)
        # self.files_added = 0

  def add_module(self, module, file_index):
    module_type = module.module_type
    # filename = module.filename
    for name, member in filter(lambda kv: _should_export_symbol(module, *kv), module.items()):
      try:
        self.symbol_dict[name].append(
            SymbolEntry(SymbolType.from_pobject_value(member.value()), module_type, file_index))
      except errors.AmbiguousFuzzyValueError:
        self.symbol_dict[name].append(SymbolEntry(SymbolType.AMBIGUOUS, module_type, file_index))

  @staticmethod
  def build_index(path):
    index = SymbolIndex()
    index.path = path
    for path in sys.path:
      index.add_path(path, ignore_init=True)
    return index


def _should_scan_file(filename, include_private_files):
  if include_private_files:
    return True
  return filename[0] != '_'


def _should_export_symbol(current_module, name, pobject):
  if name == '_' or name[:2] == '__':
    return False

  if pobject.imported:
    return False

  if isinstance(pobject, language_objects.Module):
    return False

  return True
