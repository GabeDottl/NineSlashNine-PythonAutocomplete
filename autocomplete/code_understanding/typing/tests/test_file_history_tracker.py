from pathlib import Path
import shutil
import time
import os
from ..project_analysis import file_history_tracker

STORAGE_FILE = '/tmp/fht_tmp.msg'
TEST_FILE = '/tmp/x_fht'
TEST_DIR = '/tmp/fht_dir'


def test_file_history_tracker():
  _clean()
  try:
    fht = file_history_tracker.FileHistoryTracker.load(STORAGE_FILE)
    assert not fht.has_file_changed_since_timestamp(TEST_FILE)
    Path(TEST_FILE).touch()
    assert fht.has_file_changed_since_timestamp(TEST_FILE)
    fht.update_timestamp_for_path(TEST_FILE)
    assert not fht.has_file_changed_since_timestamp(TEST_FILE)
    # Test saving and loading.
    fht.save()
    fht2 = file_history_tracker.FileHistoryTracker.load(STORAGE_FILE)
    assert not fht2.has_file_changed_since_timestamp(TEST_FILE)

    os.makedirs(TEST_DIR)
    assert not list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, None))
    filename = os.path.join(TEST_DIR, 'x')
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    Path(filename).touch()
    assert list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, None)) == [filename]
    fht.update_timestamp_for_path(filename)
    path = os.path.join(TEST_DIR, 'a', 'b', 'c', 'd')
    os.makedirs(path)
    filename = os.path.join(path, 'x')
    # Create x.
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    Path(filename).touch()
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, None, auto_update=True))
    assert files == [filename]
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, None, auto_update=True))
    assert files == []
    # Modify x.
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    Path(filename).touch()
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, None, auto_update=False))
    assert files == [filename]
    # Ensure auto_update=False works:
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, None, auto_update=True))
    assert files == [filename]
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, None, auto_update=True))
    assert files == []
    # Test filtering.
    filter_fn=lambda root, subdir: subdir != 'a'
    filename = os.path.join(TEST_DIR, 'a', 'x')
    time.sleep(0.2)  # Accounting for time.time() imprecision to ensure getmtime is after timestamp.
    Path(filename).touch()
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, filter_fn, auto_update=True))
    assert files == []
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
