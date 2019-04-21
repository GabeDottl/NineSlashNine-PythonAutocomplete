import argparse
import os
from glob import glob
from pprint import pprint

from autocomplete.code_understanding.typing import (api, collector,
                                                    module_loader)
from autocomplete.nsn_logging import info


def scan_missing_symbols(filename, include_context=False):
  api.analyze_file(filename)
  return collector.get_missing_symbols_in_file(filename, include_context=False)


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('directory_or_file')
  parser.add_argument('recursive', default=False)
  args = parser.parse_args()

  if os.path.isdir(args.directory_or_file):
    missing_map = {}
    filenames = glob(
        os.path.join(args.directory_or_file, '**/*.py'),
        recursive=args.recursive)
    for filename in filenames:
      info(f'Scanning {filename}')
      missing_map[filename] = scan_missing_symbols(filename)
    print('Missing symbol map:')
    pprint(missing_map)
  else:
    assert os.path.exists(args.directory_or_file)
    print(scan_missing_symbols(args.directory_or_file))
