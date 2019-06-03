import time
import os
import attr
from functools import partial
from ..utils import is_python_file
from typing import Generator

from ....trie import (FilePathTrie, append_sep_if_dir, remove_last_node_from_path, path_to_str)
from ....nsn_logging import info


def git_filter(root, filename):
  # TODO: directory check.
  return filename != '.git'


def python_package_filter(root, filename):
  base = os.path.join(root, filename)
  # Check filename is a python package or python file.
  return git_filter(root, filename) and ((not os.path.isdir(base) and is_python_file(base))
                                         or os.path.exists(os.path.join(base, '__init__.py')))


@attr.s
class FileHistoryTracker:
  '''In general, avoid creating this class manually in favor of calling FHT#load.'''
  save_filename = attr.ib()
  root_dir = attr.ib()
  filter_fn = attr.ib(git_filter)
  file_timestamp_trie = attr.ib(factory=FilePathTrie)

  def __attrs_post_init__(self):
    self.root_dir = append_sep_if_dir(self.root_dir)

  def save(self):
    self.file_timestamp_trie.save(self.save_filename)

  @staticmethod
  def load(save_filename, root_dir, filter_fn, lazy_create=True) -> 'FileHistoryTracker':
    if not os.path.exists(save_filename):
      if not lazy_create:
        raise ValueError(f'Invalid path for loading: {save_filename}')
      else:
        return FileHistoryTracker(save_filename, root_dir, filter_fn)
    return FileHistoryTracker(save_filename=save_filename,
                              root_dir=root_dir,
                              filter_fn=filter_fn,
                              file_timestamp_trie=FilePathTrie.load(save_filename))

  def update_timestamp_for_path(self, filename, timestamp=None):
    if timestamp is None:
      # Note: Precision may not be <1s - so it's possible if a file is modified immediately after
      # this call, it's modification time may show as being before or after this timestamp.
      # https://docs.python.org/3/library/time.html#time.time
      timestamp = time.time()
    # Store directories with trailing / to ensure we never run into messy situations where one
    # subdir string is a subset of another (e.g. /go and /google). By marking the dir, we're
    # indicating we've inspected everything we care about in the dir and thus the value set here
    # is representative of the entire subtree.
    self.file_timestamp_trie.add(filename, timestamp)

  def has_file_changed_since_timestamp(self, filename):
    '''Important: This is *not* recursive - use get_files_in_dir_modified_since_timestamp for recursion.'''
    return self.does_file_exist_and_is_not_filtered(filename) and self._modified_since_update(filename)

  def _modified_since_update(self, filename):
    return os.path.getmtime(filename) > self.file_timestamp_trie.get_value_for_string(filename)

  def does_file_exist_and_is_not_filtered(self, filename):
    if not os.path.exists(filename):
      return False
    filename = append_sep_if_dir(filename)
    if filename[:len(self.root_dir)] != self.root_dir:
      return False
    if not self.filter_fn:
      return True

    # Check filter_fn passes entire path from self.root_dir -> filename.
    relative_filename = filename[len(self.root_dir):]  # Won't include / at start.
    split = relative_filename.split(os.sep)
    path = self.root_dir
    for d in split:
      if not self.filter_fn(path, d):
        return False
      path = os.path.join(path, d)
    return True

  def get_files_in_dir_modified_since_timestamp(self, directory, auto_update=False):
    '''Gets files tracked by this beneath directory which have changed since this was last updated.

    Returns a generator yielding (updated, path).

    |updated| indicates whether the file was updated - i.e. added or modified (otherwise it was
    removed if False).
    TODO: Perhaps make this |deleted| instead.
    '''
    for root, subdirs, filenames in os.walk(directory, topdown=True):
      if self.filter_fn:
        # Note: [:] so we modify subdirs in place to avoid walking down them.
        subdirs[:] = list(filter(partial(self.filter_fn, root), subdirs))
        filenames = list(filter(partial(self.filter_fn, root), filenames))
      # Frustratingly, getmtime for an individual directory will only reflect changes directly to
      # the directory including creating/deleting files, but not modifications to them... As such,
      # we must check *every* file...
      # TODO: Find some cheaper ways to do this. Perhaps using platform-dependent call - e.g.:
      # https://stackoverflow.com/questions/4561895/how-to-recursively-find-the-latest-modified-file-in-a-directory
      for filename in filenames:
        full_filename = os.path.join(root, filename)
        if self._modified_since_update(full_filename):
          yield (True, full_filename)
          # Note: Ordering is careful here - the update should be applied *after* we've yielded the
          # file - the expected use of the API is that you get a file, update it, then get the next
          # file at which point this will mark the previous file as updated.
          if auto_update:
            self.update_timestamp_for_path(full_filename)

      # Both of these sets have already been filtered if necessary
      filename_set = set(filenames)
      subdir_set = set(f'{d}{os.sep}' for d in subdirs)
      for filename, trie_path in self.file_timestamp_trie.get_nodes_in_dir(root):
        if filename not in subdir_set and filename not in filename_set:
          # filename either no longer exists or is no longer valid as defined by our filtering func.
          # This could mean it was deleted, renamed, or the file structure changed in some important
          # way - e.g. a __init__.py was deleted making a directory no longer a valid package.
          info(f'Deleting subtree for {filename}')
          if filename[-1] == os.sep:
            base_path = f'{path_to_str(trie_path[:-1])}{trie_path[-1][0]}'
            for string in trie_path[-1][1].get_descendent_end_point_strings():
              yield (False, f'{base_path}{string}')
          else:  # Deleting non-dir - return it.
            yield (False, os.path.join(root, filename))
          remove_last_node_from_path(trie_path)

      if auto_update:
        self.update_timestamp_for_path(root)
    if auto_update:
      self.update_timestamp_for_path(directory)
