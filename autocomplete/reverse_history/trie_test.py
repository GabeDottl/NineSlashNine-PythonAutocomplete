from collections import Counter

from autocomplete.reverse_history import trie


def test_trie():
  examples = [
      'abcde', 'abcde', 'abcdf', 'abc', 'abcdfg', 'qres', 'abcde', 'abc', 'abd',
      'abd', 'abde'
  ]
  counter = Counter(examples)
  counts = dict(zip(counter.keys(), counter.values()))
  t = trie.AutocompleteTrie()
  for example in examples:
    t.add(example)
  value = t.get_best('a')

  assert value == 'abcde', value
  assert t.get_frequency(value) == counts[value]
  assert t.get_best('n') is None
  value = t.get_best('abd')
  assert value == 'abd'
  assert t.get_frequency(value) == counts[value]
  value = t.get_best('q')
  assert value == 'qres'
  assert t.get_frequency(value) == counts[value]

  t.prune_infrequent_copy(2)


if __name__ == '__main__':
  test_trie()
