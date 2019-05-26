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

  def update_timestamp_for_path(self, filename, timestamp=None):
    if timestamp is None:
      timestamp = time.time()
    # Store directories with trailing / to ensure we never run into messy situations where one
    # subdir string is a subset of another (e.g. /go and /google). By marking the dir, we're
    # indicating we've inspected everything we care about in the dir and thus the value set here
    # is representative of the entire subtree.
    if os.path.isdir(filename) and filename[-1] != os.sep:
      filename = f'{filename}{os.sep}'
    self.file_timestamp_trie.add(filename, timestamp)

  def has_file_changed_since_timestamp(self, filename):
    '''Important: This is *not* recursive - use get_files_in_dir_modified_since_timestamp for recursion.'''
    return os.path.exists(filename) and os.path.getmtime(filename) > self.file_timestamp_trie.get_value_for_string(filename)

  def get_files_in_dir_modified_since_timestamp(self, directory, filter_fn=None, auto_update=False):
    # max_last_update_timestamp = self.file_timestamp_trie[filename]
    if not filter_fn:
      filter_fn = lambda rsf: os.path.basename(rsf[0]) != '.git'
    for root, subdirs, filenames in filter(filter_fn, os.walk(directory)):
      # Frustratingly, getmtime for an individual directory will only reflect changes directly to
      # the directory including creating/deleting files, but not modifications to them... As such,
      # we must check *every* file...
      # TODO: Find some cheaper ways to do this. Perhaps using platform-dependent call - e.g.:
      # https://stackoverflow.com/questions/4561895/how-to-recursively-find-the-latest-modified-file-in-a-directory
      for filename in filenames:
        full_filename = os.path.join(root, filename)
        if self.has_file_changed_since_timestamp(full_filename):
          yield full_filename
        if auto_update:
          self.update_timestamp_for_path(full_filename)
      if auto_update:
        self.update_timestamp_for_path(root)
    if auto_update:
      self.update_timestamp_for_path(directory)
