from .. import module_loader


def test_simple_assignment():
  source = '''
a = 1
b = 2.2
c = True
d = "asdf"
e = 2j # TODO: Add support for 1+2j
class X: pass
x = X()
'''
  module = module_loader.load_module_from_source(source, __file__)
  assert module['a'].instance_of(int).truth()
  assert module['b'].instance_of(float).truth()
  assert module['c'].instance_of(bool).truth()
  assert module['d'].instance_of(str).truth()
  assert module['e'].instance_of(complex).truth()
  # assert module['x'].instance_of(module['X']).truth()


def test_function_assignment():
  source = '''
a = 1
b = 2.2
c = True
d = "asdf"
e = 2j # TODO: Add support for 1+2j
'''
  module = module_loader.load_module_from_source(source, __file__)
  # assert module['a'].instance_of(int).truth()
  # assert module['b'].instance_of(float).truth()
  # assert module['c'].instance_of(bool).truth()
  # assert module['d'].instance_of(str).truth()
  # assert module['e'].instance_of(complex).truth()



if __name__ == "__main__":
  test_simple_assignment()
  test_function_assignment
