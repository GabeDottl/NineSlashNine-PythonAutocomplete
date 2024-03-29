'''This module derives what symbols are exported from a given source.'''
import os
from argparse import ArgumentParser
from glob import glob
from typing import List

import attr
import pandas as pd

from .. import module_loader
from ....nsn_logging import info, pop_context, push_context, set_verbosity


def extract_exports(source, filename):
  module_key = module_loader.ModuleKey.from_filename(filename)
  module = module_loader.get_module_from_key(module_key)
  # frame_ = api.frame_from_source(source)
  exports = dict(filter(lambda k, v: '_' != k[0], module.items()))
  return exports


def create_symbol_index(sys_path):
  symbol_index = {}
  for path in sys_path:
    python_files = glob(os.path.join(path, '*.py'))
    for filename in python_files:
      info(f'Processing {filename}')
      name = os.path.splitext(os.path.basename(filename))[0]
      push_context(name)
      module_key = module_loader.ModuleKey.from_filename(filename)
      module = module_loader.get_module_from_key(module_key)
      pop_context()
      for symbol, value in module.items():
        if symbol not in symbol_index:
          symbol_definitions = []
          symbol_index[symbol] = symbol_definitions
        else:
          symbol_definitions = symbol_index[symbol]
        symbol_definitions.append(SymbolDefinition(module, value))
  return symbol_index


def dataframe_from_symbol_index(symbol_index):
  symbol_list, type_list, module_list = [], [], []
  for symbol, definitions in symbol_index.items():
    for definition in definitions:
      symbol_list.append(symbol)
      type_list.append(definition.value)
      module_list.append(os.path.basename(definition.module.filename))
  return pd.DataFrame({'symbol': symbol_list, 'type': type_list, 'module': module_list})


@attr.s(slots=True)
class SymbolDefinition:
  module = attr.ib()
  value = attr.ib()
  # TODO: Usages.


@attr.s(slots=True)
class Symbol:
  name = attr.ib()
  symbol_definitions: List[SymbolDefinition] = attr.ib()


if __name__ == "__main__":
  set_verbosity('info')
  parser = ArgumentParser()
  parser.add_argument('directory')
  args, _ = parser.parse_known_args()
  symbol_index = create_symbol_index([args.directory])
  df = dataframe_from_symbol_index(symbol_index)
  # pprint(extract_exports(source))
  print(f'{len(df)} symbols found.')
  print(df)
