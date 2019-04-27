from functools import wraps

import numpy as np

a = 2
b = False
c = 'string'
d = 1.2


class Klazz:
  e = 1

  @wraps(None)
  def foo(self, a, *args, b=2, **kwargs):
    return 4


k = Klazz()
g = k.foo(1)
