import os
from functools import wraps
from typing import List

from g import h


@wraps
class Example(Object):
  a: List[int] = 0

  @wraps
  @wraps2
  def __init__(self, kw_arg=1, *args, **kwargs):
    b = 1

  async def async_func(self, kw_arg=1, *args, **kwargs):
    global d
    d = 1
    q = 0

    def nonlocal_func():
      nonlocal q
      q += 1
      return q

    return 0


list_comprehension = [i for i in range(10)]
dict_comprehension = {i: i + 1 for i in range(10)}
c = True
if c:
  pass
elif not True:
  pass
else:
  pass

d = 1 if not c else 2
while True:
  break

for _ in range(10):
  continue

d += 1
a = 0


def gen():
  while True:
    yield 1


path = os.path.join('asdfasdfads', os.path.abspath(__file__))
try:
  raise Exception()
except OSError as e:
  pass
finally:
  pass

with open(path) as f:
  pass


def func(*args):
  pass


func(*list(range(10)), **dict_comprehension)
reversed = list_comprehension[::-1]
a, b = 1, 2
a += 1
example = Example()
a, (example.a, c) = 1, (2, 3)
a = 1 | 2 ^ (3 * 2 + 3**3) >> 2 & 1  # 3, apparently.
# TODO away & from
