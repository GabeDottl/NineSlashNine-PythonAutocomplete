from pathlib import Path
import shutil
import time
import os
from ..project_analysis import file_history_tracker
from ....trie import append_sep_if_dir

STORAGE_FILE = '/tmp/fht_tmp.msg'
TEST_FILE = '/tmp/fht_dir/x_fht'
TEST_DIR = '/tmp/fht_dir'


# TODO: clean this up.
def test_file_history_tracker():
  _clean()
  try:
    os.makedirs(TEST_DIR)
    fht = file_history_tracker.FileHistoryTracker.load(STORAGE_FILE, TEST_DIR, None)
    assert not fht.has_file_changed_since_timestamp(TEST_FILE)
    Path(TEST_FILE).touch()
    assert fht.has_file_changed_since_timestamp(TEST_FILE)
    fht.update_timestamp_for_path(TEST_FILE)
    assert not fht.has_file_changed_since_timestamp(TEST_FILE)
    # Test saving and loading.
    fht.save()
    fht2 = file_history_tracker.FileHistoryTracker.load(STORAGE_FILE, TEST_DIR, None)
    assert not fht2.has_file_changed_since_timestamp(TEST_FILE)
    _clean()

    os.makedirs(TEST_DIR)
    fht = file_history_tracker.FileHistoryTracker.load(STORAGE_FILE, TEST_DIR, None)
    assert not list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR))
    filename = os.path.join(TEST_DIR, 'x')
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    Path(filename).touch()
    assert list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR)) == [(True, filename)]
    fht.update_timestamp_for_path(filename)
    path = os.path.join(TEST_DIR, 'a', 'b', 'c', 'd')
    os.makedirs(path)
    filename = os.path.join(path, 'x')
    # Create x.
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    Path(filename).touch()
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == [(True, filename)]
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == []
    # Modify x.
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    Path(filename).touch()
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=False))
    assert files == [(True, filename)]
    # Ensure auto_update=False works:
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == [(True, filename)]
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == []
  finally:
    _clean()


def test_filtering_and_removal():
  try:
    # Test filtering & removal.
    _clean()
    nonpackage = os.path.join(TEST_DIR, 'nonpackage')
    os.makedirs(nonpackage)
    x = os.path.join(nonpackage, 'x.py')
    Path(x).touch()
    package = os.path.join(TEST_DIR, 'package')
    os.makedirs(package)
    package = append_sep_if_dir(package)
    init = os.path.join(package, '__init__.py')
    Path(init).touch()
    subpackage = os.path.join(package, 'subpackage')
    os.makedirs(subpackage)
    subpackage = append_sep_if_dir(subpackage)
    subpackage_init = os.path.join(subpackage, '__init__.py')
    Path(subpackage_init).touch()
    subpackage2 = os.path.join(package, 'subpackage2')
    os.makedirs(subpackage2)
    subpackage2 = append_sep_if_dir(subpackage2)
    subpackage2_init = os.path.join(subpackage2, '__init__.py')
    Path(subpackage2_init).touch()
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    fht = file_history_tracker.FileHistoryTracker.load(STORAGE_FILE, TEST_DIR,
                                                       file_history_tracker.python_package_filter)
    # filename = os.path.join(TEST_DIR, 'a', 'x')
    # Path(filename).touch()
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert set(files) == set([(True, init), (True, subpackage_init), (True, subpackage2_init)])
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == []
    y = os.path.join(package, 'y.py')
    Path(y).touch()
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == [(True, y)]
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    shutil.rmtree(nonpackage)
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == []
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == []
    shutil.rmtree(subpackage)
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == [(False, subpackage_init)]
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    shutil.rmtree(package)
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    # Package contents recursively should be removed.
    assert set(files) == set([(False, package), (False, init), (False, subpackage2),
                              (False, subpackage2_init), (False, y), (False, init)])
  finally:
    _clean()


def _clean():
  if os.path.exists(STORAGE_FILE):
    os.remove(STORAGE_FILE)
  if os.path.exists(TEST_FILE):
    os.remove(TEST_FILE)
  if os.path.exists(TEST_DIR):
    shutil.rmtree(TEST_DIR)


if __name__ == "__main__":
  test_file_history_tracker()
  test_filtering_and_removal()
