def assert_expected_iterable(actual, expected):
  actual = set(actual)
  expected = set(expected)
  difference = actual.difference(expected)
  assert not difference, difference  # Should be empty set.
