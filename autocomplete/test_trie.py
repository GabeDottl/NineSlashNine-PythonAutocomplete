from collections import Counter
import os
import glob

from .trie import Trie, FilePathTrie


def test_trie():
  examples = [
      'ab', 'abcde', 'ab', 'abcde', 'abcdf', 'abc', 'ab', 'abcdfg', 'ab', 'ab', 'qres', 'abcde', 'abc', 'abd',
      'abd', 'abde'
  ]
  counter = Counter(examples)
  counts = dict(zip(counter.keys(), counter.values()))

  t = Trie()
  for example in examples:
    t.add(example, 1, add_value=True)

  value = t.get_max('a')
  assert value == 'ab', value
  assert t.get_value_for_string(value) == counts[value]
  assert t.get_max('n') is None

  t.remove('ab', remove_subtree=False)
  value = t.get_max('a')
  assert value == 'abcde', value
  assert t.get_value_for_string(value) == counts[value]

  value = t.get_max('q')
  assert value == 'qres'
  assert t.get_value_for_string(value) == counts[value]

  t.copy_with_lower_values_pruned(2)


def test_trie_with_file_tree():
  base_dir = os.path.join(os.getenv('CODE'),
                          'autocomplete')  #, 'autocomplete', 'code_understanding', 'typing')
  assert os.path.exists(base_dir)
  directories = set()
  trie = FilePathTrie()
  paths = glob.glob(os.path.join(base_dir, '**', '*.py'), recursive=True)
  for path in paths:
    full_path = os.path.join(base_dir, path)
    directories.add(os.path.dirname(full_path))
    trie.add(full_path, value=os.path.getmtime(full_path))
  assert trie.get_value_for_string(__file__)
  directory_removed = os.path.dirname(__file__)
  trie.remove(directory_removed)
  assert not trie.get_value_for_string(__file__)
  assert not trie.get_max(os.path.dirname(full_path))
  # OS should be essentially doing similar behaviour with getmtime for directories - check.
  TMP_PATH = '/tmp/tmp_trie.msg'
  trie.save(TMP_PATH)
  trie_loaded = FilePathTrie.load(TMP_PATH)
  # Check things work for both the original trie and the loaded one.
  # TODO: Perhaps just replace this with some equals check....
  for t in (trie, trie_loaded):
    for directory in directories:
      if directory_removed == directory[:len(directory_removed)]:
        continue
      max_file = t.get_max(directory)
      assert max_file
      assert t.get_max_value_at_or_beneath_prefix(directory) == os.path.getmtime(max_file)


if __name__ == '__main__':
  test_trie()
  test_trie_with_file_tree()
