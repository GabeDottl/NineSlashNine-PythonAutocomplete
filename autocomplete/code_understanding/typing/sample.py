class Foo:
  x = 1
  def __init__(self):
    self.y = 2

  def foofie(self):
    print(x)
    print(self.x)

  def inter(self):
    return 1

x = 'str'
foo = Foo()
foo.foofie()
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
