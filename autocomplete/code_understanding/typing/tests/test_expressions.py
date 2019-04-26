from autocomplete.code_understanding.typing import module_loader
from autocomplete.code_understanding.typing.pobjects import FuzzyBoolean


def test_dicts():
  source = '''
a={"a": 1}
b={"b": 1}
d = {**a, **b}
b={"b":i for i in range(1)}
c = {**a, **b, "c":1}
'''
  module = module_loader.load_module_from_source(source)
  assert module['a'].value() == {"a": 1}
  assert module['d'].value() == {"a": 1, "b": 1}
  # TODO
  # assert module['b'].value() == {"b": 1}
  # assert module['c'].value() == {"a": 1, "b": 1, "c": 1}


def test_sets():
  source = '''
  a={"a"}
  b={"b"}
  d = {*a, *b}
  b={"b" for i in range(1)}
  c = {*a, *b, "c"}
  '''
  module = module_loader.load_module_from_source(source)
  # TODO
  # assert module['a'].value() == {"a"}
  # assert module['d'].value() == {"a", "b"}
  # assert module['b'].value() == {"b"}
  # assert module['c'].value() == {"a", "b", "c"}


def test_and_or():
  source = '''
  a = False
  def foo(): return True
  b = a or foo()
  c = a and foo()
  d = not a or not foo() and b
  e = foo() and not foo() and foo()

  '''
  module = module_loader.load_module_from_source(source)
  assert not module['a'].value()
  assert module['b'].bool_value() == FuzzyBoolean.TRUE
  assert module['c'].bool_value() == FuzzyBoolean.FALSE
  assert module['d'].bool_value() == FuzzyBoolean.TRUE
  assert module['e'].bool_value() == FuzzyBoolean.FALSE


if __name__ == '__main__':
  test_dicts()
  test_sets()
  test_and_or()
