from .. import refactor


def test_refactor():
  source = '''1
line1
line2

'''
  target_source = '''
aa
good1
ltestine2
bucket
'''
  replacements = [refactor.Replace((1, 0), (1, 4), 'good')]
  inserts = [
      refactor.Insert((0, 0), 'a'),
      refactor.Insert((0, 0), 'a'),
      refactor.Insert((2, 1), 'test'),
      refactor.Insert((3, 0), 'bucket'),
      refactor.Insert((0, 0), '\n')
  ]
  removals = [refactor.Delete((0, 0), (0, 1))]
  result = refactor.apply_changes_to_string(source, replacements, inserts, removals)
  print(result)
  assert result == target_source


if __name__ == "__main__":
  test_refactor()
