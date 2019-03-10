from autocomplete.reverse_history import trie

def test_trie():
  examples = ['abcde', 'abcde', 'abcdf', 'abc', 'abcdfg', 'qres', 'abcde', 'abc', 'abd', 'abd', 'abde']
  t = trie.AutocompleteTrie()
  for example in examples:
    t.add(example)
  value = t.get_best('a')
  assert value == 'abcde', value
  assert t.get_frequency(value) == 3
  assert t.get_best('n') is None
  value = t.get_best('abd')
  assert value == 'abd'
  assert t.get_frequency(value) == 2

if __name__ == '__main__':
  test_trie()
