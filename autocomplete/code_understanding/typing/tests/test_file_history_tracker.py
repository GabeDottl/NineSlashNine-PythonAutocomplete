from pathlib import Path
import shutil
import os
from ..project_analysis import file_history_tracker

STORAGE_FILE = '/tmp/fht_tmp.msg'
TEST_FILE = '/tmp/x_fht'
TEST_DIR = '/tmp/fht_dir'


def test_file_history_tracker():
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
    assert not list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR))
    filename = os.path.join(TEST_DIR, 'x')
    Path(filename).touch()
    assert list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR)) == [filename]
    fht.update_timestamp_for_path(filename)
    path = os.path.join(TEST_DIR, 'a', 'b', 'c', 'd')
    os.makedirs(path)
    filename = os.path.join(path, 'x')
    # Create x.
    Path(filename).touch()
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == [filename]
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == []
    # Modify x.
    Path(filename).touch()
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=False))
    assert files == [filename]
    # Ensure auto_update=False works:
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == [filename]
    files = list(fht.get_files_in_dir_modified_since_timestamp(TEST_DIR, auto_update=True))
    assert files == []

  finally:
    if os.path.exists(STORAGE_FILE):
      os.remove(STORAGE_FILE)
    if os.path.exists(TEST_FILE):
      os.remove(TEST_FILE)
    if os.path.exists(TEST_DIR):
      shutil.rmtree(TEST_DIR)


if __name__ == "__main__":
  test_file_history_tracker()