import os

from autocomplete.code_understanding.typing.project_analysis import (
    symbol_exports)


def test_missing_symbols():
  typing_dir = os.path.join(os.path.dirname(__file__), '..')
  unresolved_imports_filename = os.path.join(typing_dir, 'examples',
                                             'unresolved_symbols.py')
  missing_symbols = symbol_exports.scan_missing_symbols(
      unresolved_imports_filename)
  # Should be missing unresolved 1 - 4.
  assert len(missing_symbols) == 4, missing_symbols
  for i in range(1, 5):
    assert f'unresolved{i}' in missing_symbols


if __name__ == "__main__":
  test_missing_symbols()
