def bar(a, b, c):
  return a * (b - c)


out = bar(1, c=3, b=2)
c = 3


class AClass:
  a = 1

  def __init__(self, b):
    self.b = c

  def get_b(self):
    return self.b


a = AClass(1)

b = a.get_b()
c = b + 2

if b > 4:
  d = 1
else:
  d = 'boo'
