import os

from autocomplete.nsn_logging import info
from autocomplete.code_understanding.typing import symbol_index

HOME = os.getenv('HOME')
INDEX_PATH = f'{HOME}/index.msg'


def test_build_typing_index():
  index = symbol_index.SymbolIndex.build_index_from_package(
      INDEX_PATH, f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing')
  symbol_entries = index.find_symbol('Function')
  assert len(symbol_entries) == 1
  assert symbol_entries[0].symbol_type == symbol_index.SymbolType.TYPE
  index.save(INDEX_PATH)
  info(f'Built package index. {len(index.normal_module_list)} modules.')
  # Ensure it loaded as expected without crashing.
  symbol_index.SymbolIndex().load(INDEX_PATH)


def test_add_file():
  index = symbol_index.SymbolIndex()
  index.add_file(f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing/test.py')

# Commented out so pytest doesn't run on it.
# def test_build_full_index():
#   index = symbol_index.SymbolIndex.build_index(INDEX_PATH)
#   index.save(INDEX_PATH)


# def test_save_load_index():
#   index = symbol_index.SymbolIndex()
#   index.add_file(f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing/test.py')

  

if __name__ == "__main__":
  test_build_typing_index()
  # test_load_index()
  # test_build_full_index()
