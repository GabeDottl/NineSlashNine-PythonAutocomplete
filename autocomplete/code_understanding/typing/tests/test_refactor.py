from .. import refactor


def test_refactor():
  source = '''1
line1
line2

'''
  target_source = '''
aa1
ltestine2
bucket'''
  inserts = [
      refactor.Insert((0, 0), 'a'),
      refactor.Insert((0, 0), 'a'),
      refactor.Insert((2, 1), 'test'),
      refactor.Insert((3, 0), 'bucket'),
      refactor.Insert((0, 0), '\n')
  ]
  removals = [refactor.Remove((1, 0), (1, -1))]
  result = refactor.apply_inserts_and_removals_to_string(source, inserts, removals)
  print(result)
  assert result == target_source


if __name__ == "__main__":
  test_refactor()
