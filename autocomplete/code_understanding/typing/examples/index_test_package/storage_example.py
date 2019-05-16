import sys
import traceback

import six  # NativeModule

from .boo import Boo

a = 2
b = False
c = 'string'
d = 1.2


class Klazz:
  e = 1

  def foo(self, a, *args, b=2, **kwargs):
    return Boo()


k = Klazz()
g = k.foo(1)