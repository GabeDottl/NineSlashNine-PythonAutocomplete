'''This module derives what symbols are exported from a given source.'''
import os
from argparse import ArgumentParser
from glob import glob
from pprint import pprint
from typing import List

import attr
import pandas as pd

from autocomplete.code_understanding.typing import (api, collector,
                                                    module_loader)
from autocomplete.nsn_logging import (info, pop_context, push_context,
                                      set_verbosity)


def extract_exports(source, filename):
  frame_ = api.frame_from_source(source)
  exports = dict(filter(lambda k, v: '_' != k[0], frame_._locals))
  return exports


def scan_missing_symbols(filename):
  collector_ = api.analyze_file(filename)
  return collector.get_missing_symbols_in_file(filename)


def create_symbol_index(sys_path):
  symbol_index = {}
  for path in sys_path:
    python_files = glob(os.path.join(path, '*.py'))
    for filename in python_files:
      info(f'Processing {filename}')
      name = os.path.splitext(os.path.basename(filename))[0]
      push_context(name)
      module = module_loader.get_module_from_filename(name, filename)
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
  return pd.DataFrame({
      'symbol': symbol_list,
      'type': type_list,
      'module': module_list
  })


@attr.s
class SymbolDefinition:
  module = attr.ib()
  value = attr.ib()
  # TODO: Usages.


@attr.s
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
