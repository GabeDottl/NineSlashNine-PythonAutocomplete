import argparse
import os
from glob import glob
from pprint import pprint
from itertools import chain

from autocomplete.code_understanding.typing import (api, collector, module_loader, utils, language_objects)
from autocomplete.code_understanding.typing.control_flow_graph_nodes import (FromImportCfgNode)
from autocomplete.nsn_logging import info


def scan_missing_symbols_in_file(filename):
  # TODO: Add some platform configuration.
  with open(filename) as f:
    source = ''.join(f.readlines())
  graph = api.graph_from_source(source)
  return scan_missing_symbols_in_graph(graph, os.path.dirname(filename))


def scan_missing_symbols_in_graph(graph, directory=None):
  missing_symbols = graph.get_non_local_symbols()
  for builtin in chain(utils.get_possible_builtin_symbols(), language_objects.ModuleImpl.get_module_builtin_symbols()):
    if builtin in missing_symbols:
      del missing_symbols[builtin]
  # The above method will find a superset of the actual missing symbols using pure static-analysis. Some of
  # these symbols may not actually be missing during interpretation because either they're imported with
  # a glob import (from a import *) or they're manually set as attributes on the module (setattr(__module__)).
  # TODO: Handle setattr(__module__) case / do full interpretation.
  if missing_symbols:
    # Check for wild-card/glob imports - i.e. 'from a import *'.
    from_imports = graph.get_descendents_of_types(FromImportCfgNode)
    for from_import in from_imports:
      for imported_symbol in from_import.imported_symbol_names():
        if imported_symbol == '*':
          # Get obvious exported symbols - similar to mentioned above, the module could theoretically have
          # attributes set on it externally or via setattr, but this would be quite odd and we assume doesn't
          # happen.
          filename, _, _ = module_loader.get_module_info_from_name(from_import.module_path, directory)
          # TODO: Cache graph.
          with open(filename) as f:
            imported_graph = api.graph_from_source(''.join(f.readlines()))
            defined_symbols = set(imported_graph.get_defined_and_exported_symbols())
            missing_symbols = {
                s: c
                for s, c in filter(lambda sc: not sc[0] in defined_symbols, missing_symbols.items())
            }
          # Early return where possible.
          if not missing_symbols:
            return missing_symbols
  return missing_symbols


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('directory_or_file')
  parser.add_argument('recursive', default=False)
  args = parser.parse_args()

  if os.path.isdir(args.directory_or_file):
    missing_map = {}
    filenames = glob(os.path.join(args.directory_or_file, '**/*.py'), recursive=args.recursive)
    for filename in filenames:
      info(f'Scanning {filename}')
      missing_map[filename] = scan_missing_symbols_in_file(filename)
    print('Missing symbol map:')
    pprint(missing_map)
  else:
    assert os.path.exists(args.directory_or_file)
    print(scan_missing_symbols_in_file(args.directory_or_file))
