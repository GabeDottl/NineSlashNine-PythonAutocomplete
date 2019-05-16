import os

from .. import symbol_index
from ....nsn_logging import info

HOME = os.getenv('HOME')
INDEX_PATH = f'/tmp/index.msg'


def test_build_test_index():
  index = symbol_index.SymbolIndex.build_index_from_package(
      f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing/examples/index_test_package',
      INDEX_PATH)
  index.save(INDEX_PATH)
  entries = sorted(index.find_symbol('attr'), key=lambda e: e.import_count)
  entry = entries[-1]
  assert not entry.imported and entry.symbol_type == symbol_index.SymbolType.MODULE and entry.import_count == 2
  info(f'Built package index. {len(index.normal_module_list)} modules.')
  # Ensure it loaded as expected without crashing.
  symbol_index.SymbolIndex().load(INDEX_PATH)


def test_build_typing_index():
  index = symbol_index.SymbolIndex.build_index_from_package(
      f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing', INDEX_PATH)
  symbol_entries = list(filter(lambda x: not x.imported, index.find_symbol('Function')))
  assert len(symbol_entries) == 1
  assert symbol_entries[0].symbol_type == symbol_index.SymbolType.TYPE
  index.save(INDEX_PATH)
  entries = sorted(index.find_symbol('attr'), key=lambda e: e.import_count)
  entry = entries[-1]
  # Ensure that
  assert not entry.imported and entry.symbol_type == symbol_index.SymbolType.MODULE and entry.import_count > 5
  # entries = index.find_symbol('attr')
  # assert entries[0].imported and entries[0].symbol_type == symbol_index.SymbolType.MODULE
  info(f'Built package index. {len(index.normal_module_list)} modules.')
  # Ensure it loaded as expected without crashing.
  symbol_index.SymbolIndex().load(INDEX_PATH)


def test_add_file():
  initial_index = symbol_index.SymbolIndex(INDEX_PATH)
  initial_index.add_file(
      f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing/examples/index_test_package/boo.py',
      track_imported_modules=True)
  initial_index.process_tracked_imports()
  initial_index.save()
  loaded_index = symbol_index.SymbolIndex.load(INDEX_PATH)

  # index.add_path(
  #     f'/usr/local/lib/python3.6/site-packages/numpy')
  for index in (initial_index, loaded_index):
    entries = list(filter(lambda x: not x.imported(), index.find_symbol('attr')))
    assert len(entries) == 1 and entries[0].is_module_itself() and 'attr' in entries[0].get_module_key(
    ).path and entries[0].get_symbol_type() == symbol_index.SymbolType.MODULE
    entries = list(filter(lambda x: not x.imported(), index.find_symbol('at')))
    assert len(entries) == 1 and entries[0].is_module_itself() and 'attr' in entries[0].get_module_key(
    ).path and entries[0].get_symbol_type() == symbol_index.SymbolType.MODULE
    entries = list(index.find_symbol('attrib'))
    assert len(entries) >= 1 and not entries[0].is_module_itself() and 'attr' in entries[0].get_module_key(
    ).path and entries[0].get_symbol_type() == symbol_index.SymbolType.FUNCTION

  #     track_imported_modules=True)


# Commented out so pytest doesn't run on it.
# def test_build_full_index():
#   index = symbol_index.SymbolIndex.build_index(INDEX_PATH)
#   index.save(INDEX_PATH)

# def test_save_load_index():
#   index = symbol_index.SymbolIndex()
#   index.add_file(f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing/test.py')

if __name__ == "__main__":
  test_add_file()
  # test_build_test_index()
  # test_build_typing_index()

  # test_build_full_index()