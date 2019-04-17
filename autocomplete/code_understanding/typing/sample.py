from collections import namedtuple


class Foo:
  x = 1
  T = namedtuple('T', ['y'])
  t = T(y=2)

  def __init__(self):
    self.y = 2
    self.t.y = 3

  def foofie(self):
    print(x)
    print(self.x)

  def get_t(self):
    return t

  def inter(self):
    return 1


1 + 1
2 + 2
3
a, b = 1, 2
x = 'str'
x + 'a'
foo = Foo()
foo.foofie()
foo.get_t().y = 3
bar = Foo()
for _ in range(10):
  if isinstance(bar, Foo):
    bar = 1
  else:
    bar = Foo()


def should_return_1(f):
  return f.inter()


z = should_return_1(foo)
# q = should_return_1(0)
