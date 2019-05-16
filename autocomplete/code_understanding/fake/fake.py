# Comment.
import glob

import autocomplete.code_understanding.fake3 as fake3
import numpy as np
from .fake2 import a_func

print(f'executed {__file__}')

x = np.arange(10)
zoo = 'module'
cookoo = 'cookoo_str'


class Foo:
  '''Multiline

  Foo docstring.'''

  def __init__(self):
    self.monster = None
    pass

  def bar(self):
    zoo = 'function'
    for _ in range(10):
      pass
    print(zoo)
    print(zoo)
    print(cookoo)

  class Boo:  # inner class
    def test(self):
      pass


def bar():
  pass


tmp = Foo()
tmp.bar()
tmp = 2
tmp2 = Foo.Boo()
Foo.Boo.test(tmp2)
fake3.another_func()
a_func()
print(zoo)
print(tmp)
print(cookoo)
print('cookoo_str')
