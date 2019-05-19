from .. import (language_objects, api, module_loader)


def test_simple_assignment():
  source = '''
a = 1
b = 2.2
c = True
d = "asdf"
'''
  module = module_loader.load_module_from_source(source, __file__)


  if __name__ == "__main__":
      test_simple_assignment