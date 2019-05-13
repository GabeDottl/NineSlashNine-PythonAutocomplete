from pathlib import Path
import os
from autocomplete.code_understanding.typing.project_analysis import file_history_tracker

STORAGE_FILE = '/tmp/fht_tmp.msg'
TEST_FILE = '/tmp/x_fht'

def test_file_history_tracker():
  if os.path.exists(STORAGE_FILE):
    os.remove(STORAGE_FILE)
  if os.path.exists(TEST_FILE):
    os.remove(TEST_FILE)
  
  fht = file_history_tracker.FileHistoryTracker.load(STORAGE_FILE)
  assert fht.has_file_changed_since_timestamp(TEST_FILE)
  Path(TEST_FILE).touch()
  assert fht.has_file_changed_since_timestamp(TEST_FILE)
  fht.update_timestamp_for_file(TEST_FILE)
  assert not fht.has_file_changed_since_timestamp(TEST_FILE)
  # Test saving and loading
  fht.save()
  fht2 = file_history_tracker.FileHistoryTracker.load(STORAGE_FILE)
  assert not fht2.has_file_changed_since_timestamp(TEST_FILE)
  # Cleanup.
  os.remove(STORAGE_FILE)
  os.remove(TEST_FILE)

if __name__ == "__main__":
    test_file_history_tracker()