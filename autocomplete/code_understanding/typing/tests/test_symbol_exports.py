import os

from autocomplete.code_understanding.typing import collector
from autocomplete.code_understanding.typing.project_analysis import (
    find_missing_symbols)


def test_missing_symbols():
  typing_dir = os.path.join(os.path.dirname(__file__), '..')
  unresolved_imports_filename = os.path.join(typing_dir, 'examples',
                                             'unresolved_symbols.py')
  missing_symbols = find_missing_symbols.scan_missing_symbols(
      unresolved_imports_filename, include_context=False)
  print('Used symbols:',
        collector._referenced_symbols[unresolved_imports_filename])
  # Should be missing unresolved 1 - 4.
  assert len(missing_symbols) == 5, missing_symbols
  for i in range(1, 6):
    assert f'unresolved{i}' in missing_symbols


if __name__ == "__main__":
  test_missing_symbols()
