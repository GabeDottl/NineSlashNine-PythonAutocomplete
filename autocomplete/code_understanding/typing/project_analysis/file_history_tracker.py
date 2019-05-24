import msgpack
import time
import os
import attr
from glob import glob

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

  def update_timestamp_for_path(self, filename, timestamp=None):
    if timestamp is None:
      timestamp = time.time()
    # Store directories with trailing / to ensure we never run into messy situations where one
    # subdir string is a subset of another (e.g. /go and /google). By marking the dir, we're
    # indicating we've inspected everything we care about in the dir and thus the value set here
    # is representative of the entire subtree.
    if os.path.isdir(filename) and filename[-1] != os.sep:
      filename = f'{filename}{os.sep}'
    self.file_timestamp_trie[filename] = timestamp

  def has_file_changed_since_timestamp(self, filename):
    return os.path.exists(filename) and os.path.getmtime(filename) > self.file_timestamp_trie.get_value_for_string(filename)

  def get_files_in_dir_modified_since_timestamp(self, directory, filter_fn=None):
    # max_last_update_timestamp = self.file_timestamp_trie[filename]
    if not filter_fn:
      filter_fn = lambda rsf: os.path.basename(rsf[0]) != '.git'
    for root, subdirs, filenames in filter(filter_fn, os.walk(directory)):
      # We explicitly check the dir value instead of max subtree-value because we may have
      # inspected only a portion of the subtree beneath the current dir.
      if not self.has_file_changed_since_timestamp(f'{root}{os.sep}'):
        continue
      # Need to check files because either the directory itself or one of them has been updated.
      for filename in filenames:
        full_filename = os.path.join(root, filename)
        if self.has_file_changed_since_timestamp(full_filename):
          yield full_filename