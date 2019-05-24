import msgpack
import time
import os
import attr

from ....trie import Trie


@attr.s
class FileHistoryTracker:
  save_filename = attr.ib()
  file_timestamp_trie = attr.ib(factory=Trie)

  def save(self):
    self.file_timestamp_trie.save(self.save_filename)

  @staticmethod
  def load(filename, lazy_create=True) -> 'FileHistoryTracker':
    if not os.path.exists(filename):
      if not lazy_create:
        raise ValueError(f'Invalid path for loading: {filename}')
      else:
        return FileHistoryTracker(filename)
    return FileHistoryTracker(filename, Trie.load(filename))
    

  def update_timestamp_for_file(self, filename, timestamp=None):
    if timestamp is None:
      timestamp = time.time()
    # Store directories with trailing / to ensure we never run into messy situations where one
    # subdir string is a subset of another (e.g. /go and /google).
    if os.path.isdir(filename) and filename[-1] != os.sep:
      filename = f'{filename}{os.sep}'
    self.file_timestamp_trie[filename] = timestamp

  def has_file_changed_since_timestamp(self, filename):
    if filename not in self.file_timestamp_trie:
      return True

    modified_timestamp = os.path.getmtime(filename)
    last_update_timestamp = self.file_timestamp_trie[filename]
    return modified_timestamp > last_update_timestamp
