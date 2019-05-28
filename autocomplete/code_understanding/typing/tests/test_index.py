import os
import shutil
from pathlib import Path
import time

from .. import symbol_index

HOME = os.getenv('HOME')
TYPING_DIR = os.path.join(os.path.dirname(__file__), '..')
INDEX_PATH = f'/tmp/index'
TMP_DIR = '/tmp'

def _clean():
  if os.path.exists(INDEX_PATH):
    shutil.rmtree(INDEX_PATH)

def test_build_test_index():
  _clean()
  index = symbol_index.SymbolIndex.build_index_from_package(
      os.path.join(TYPING_DIR, 'examples', 'index_test_package'), INDEX_PATH)
  index.save()
  entries = sorted(index.find_symbol('attr'), key=lambda e: e.get_import_count())
  entry = entries[-1]
  assert not entry.is_imported() and entry.get_symbol_type(
  ) == symbol_index.SymbolType.MODULE and entry.get_import_count() == 2
  # info(f'Built package index. {len(index.module_keys)} modules.')
  # Ensure it loaded as expected without crashing.
  symbol_index.SymbolIndex.load(INDEX_PATH)


def test_build_typing_index():
  _clean()
  index = symbol_index.SymbolIndex.build_index_from_package(TYPING_DIR, INDEX_PATH)
  symbol_entries = list(filter(lambda x: not x.is_imported(), index.find_symbol('Function')))
  assert len(symbol_entries) == 1
  assert symbol_entries[0].get_symbol_type() == symbol_index.SymbolType.TYPE
  index.save()
  entries = sorted(index.find_symbol('attr'), key=lambda e: e.get_import_count())
  entry = entries[-1]
  # Ensure that
  assert not entry.is_imported() and entry.get_symbol_type(
  ) == symbol_index.SymbolType.MODULE and entry.get_import_count() > 5
  # entries = index.find_symbol('attr')
  # assert entries[0].imported and entries[0].symbol_type == symbol_index.SymbolType.MODULE
  # info(f'Built package index. {len(index.module_keys)} modules.')
  # Ensure it loaded as expected without crashing.
  symbol_index.SymbolIndex.load(INDEX_PATH)


def test_add_file():
  _clean()
  initial_index = symbol_index.SymbolIndex.create_index(INDEX_PATH)
  initial_index.add_file(os.path.join(TYPING_DIR, 'examples', 'index_test_package', 'boo.py'))
  initial_index.save()
  loaded_index = symbol_index.SymbolIndex.load(INDEX_PATH)

  for index in (initial_index, loaded_index):
    # Note: Because we're only adding a file without tracking, for both of these entries they're
    # simply what has been imported into boo.py.
    entries = list(index.find_symbol('attr'))
    assert len(entries) == 1 and entries[0].get_symbol_type() == symbol_index.SymbolType.MODULE and entries[0].is_imported()
    entries = list(index.find_symbol('at'))
    assert len(entries) == 1 and entries[0].get_symbol_type() == symbol_index.SymbolType.MODULE  and entries[0].is_imported()


def test_micro_index_lifecycle():
  PROJECT_PATH = os.path.join(TMP_DIR, 'project')
  A = os.path.join(PROJECT_PATH, 'a')
  A_CHILD = os.path.join(A, 'test')
  B = os.path.join(PROJECT_PATH, 'b')
  B_CHILD = os.path.join(B, 'q')
  C = os.path.join(PROJECT_PATH, 'c')
  C_CHILD = os.path.join(C, 'd')
  if os.path.exists(PROJECT_PATH):
    shutil.rmtree(PROJECT_PATH)
  try:
    for d in [A, A_CHILD, B, B_CHILD, C, C_CHILD]:
      os.makedirs(d)
      Path(os.path.join(d, '__init__.py')).touch()
    index = symbol_index.SymbolIndex.build_index_from_package(A,
                                                              os.path.join(PROJECT_PATH, 'nsn_index'),
                                                              sys_path=[])
    # index.add_path(A)
    assert len(list(index.find_symbol('a'))) == 1
    assert len(list(index.find_symbol('test'))) == 1
    # Ensure nothing is updated when nothing has changed.
    assert index.update(A, True) == 0
    # Ensure touching a file triggers an update only for that file.
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    Path(os.path.join(A, '__init__.py')).touch()
    assert index.update(A, True) == 1
    # Ensure adding a file triggers an update.
    Path(os.path.join(A, 'x.py')).touch()
    assert index.update(A, True) == 1
    assert len(list(index.find_symbol('x'))) == 1
    y_py = os.path.join(A_CHILD, 'y.py')
    with open(y_py, 'w') as f:
      f.writelines('a=1')
    assert len(list(index.find_symbol('b'))) == 0
    index.add_path(B)
    assert len(list(index.find_symbol('b'))) == 1
    # Add y.py.
    assert index.update(A, True) == 1
    assert len(list(index.find_symbol('a'))) == 2
    assert len(list(index.find_symbol('y'))) == 1
    source = '''
from .test import y
'''
    x_py = os.path.join(A, 'x.py')
    with open(x_py, 'w') as f:
      f.writelines(source)
    assert index.update(A, True) == 1
    assert len(list(index.find_symbol('x'))) == 1
    y_entries = list(index.find_symbol('y'))
    assert len(y_entries) == 2
    # TODO: Make sure we pick the right symbol entry here - this might break randomly.
    assert y_entries[0].get_import_count() == 1
    # Remove x.py.
    os.remove(x_py)
    assert index.update(A, True) == 1
    # No more references to y.
    assert y_entries[0].get_import_count() == 0
    assert len(list(index.find_symbol('y'))) == 1
    assert len(list(index.find_symbol('x'))) == 0

  finally:
    if os.path.exists(PROJECT_PATH):
      shutil.rmtree(PROJECT_PATH)


# Commented out so pytest doesn't run on it.
# def test_build_full_index():
#   index = symbol_index.SymbolIndex.build_index(INDEX_PATH)
#   index.save(INDEX_PATH)

# def test_save_load_index():
#   index = symbol_index.SymbolIndex()
#   index.add_file(f'{HOME}/code/autocomplete/autocomplete/code_understanding/typing/test.py')

if __name__ == "__main__":
  if os.path.exists(INDEX_PATH):
    shutil.rmtree(INDEX_PATH)
  test_micro_index_lifecycle()
  test_add_file()
  test_build_test_index()
  test_build_typing_index()
  # test_build_full_index()
