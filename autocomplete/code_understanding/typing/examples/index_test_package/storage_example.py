a = 2
b = False
c = 'string'
d = 1.2


class Klazz:
  e = 1

  def foo(self, a, *args, b=2, **kwargs):
    from .boo import Boo
    return Boo()


k = Klazz()
# g = k.foo(1)
