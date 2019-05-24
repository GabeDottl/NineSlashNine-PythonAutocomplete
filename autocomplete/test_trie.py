from collections import Counter
import os
import glob

from .trie import Trie


def test_trie():
  examples = ['abcde', 'abcde', 'abcdf', 'abc', 'abcdfg', 'qres', 'abcde', 'abc', 'abd', 'abd', 'abde']
  counter = Counter(examples)
  counts = dict(zip(counter.keys(), counter.values()))

  t = Trie()
  for example in examples:
    t.add(example, 1, add_value=True)

  value = t.get_max('a')
  assert value == 'abcde', value
  assert t.get_value_for_string(value) == counts[value]
  assert t.get_max('n') is None

  value = t.get_max('abd')
  assert value == 'abd'
  assert t.get_value_for_string(value) == counts[value]

  value = t.get_max('q')
  assert value == 'qres'
  assert t.get_value_for_string(value) == counts[value]

  t.copy_with_lower_values_pruned(2)

def test_trie_with_file_tree():
  base_dir = os.path.join(os.getenv('CODE'), 'autocomplete')#, 'autocomplete', 'code_understanding', 'typing')
  assert os.path.exists(base_dir)
  paths = glob.glob(os.path.join(base_dir, '**','*.py'), recursive=True)
  directories = set()
  trie = Trie()
  for path in paths:
    full_path = os.path.join(base_dir, path)
    directories.add(os.path.dirname(full_path))
    trie.add(full_path, value=os.path.getmtime(full_path))

  # OS should be essentially doing similar behaviour with getmtime for directories - check.
  TMP_PATH = '/tmp/tmp_trie.msg'
  trie.save(TMP_PATH)
  trie_loaded = Trie.load(TMP_PATH)
  # Check things work for both the original trie and the loaded one.
  # TODO: Perhaps just replace this with some equals check....
  for t in (trie, trie_loaded):
    for directory in directories:
      # Cannot guarantee this because we recurse down the tree whereas getmtime doesn't.
      # assert t.get_max_value_at_or_beneath_prefix(directory) <= os.path.getmtime(directory)
      max_file = t.get_max(directory)
      assert max_file
      assert t.get_max_value_at_or_beneath_prefix(directory) == os.path.getmtime(max_file)

if __name__ == '__main__':
  test_trie()
  test_trie_with_file_tree()