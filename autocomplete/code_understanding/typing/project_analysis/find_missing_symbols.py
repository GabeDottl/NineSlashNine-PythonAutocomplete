import argparse

from autocomplete.code_understanding.typing import api, collector, module_loader
import os
from glob import glob


def scan_missing_symbols(filename):
  api.analyze_file(filename)
  return collector.get_missing_symbols_in_file(filename)

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('directory_or_file')
  parser.add_argument('recursive', default=False)
  args = parser.parse_args()

  if os.path.isdir(args.directory_or_file):
    filenames = glob(os.path.join(args.directory_or_file, '**/*.py'), recursive=args.recursive)
    for filename in filenames:
      print(scan_missing_symbols(filename))
  else:
    assert os.path.exists(args.directory_or_file)
    print(scan_missing_symbols(args.directory_or_file))

