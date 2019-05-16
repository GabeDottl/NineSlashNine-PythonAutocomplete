# import glob.glob as blob
# import os as whatever
# from functools import wraps
# from typing import List

# import numpy

# import a.b.c
# import django as dj
# from a import a
# from a import b as c
# from a import d
# from g import h, w
# from x.y.z import q
# from x.y.z import r as s
#
# from autocomplete.code_understanding.typing.code_understanding import typing

# def bar(a, b, c):
#   return a * (b - c)
#
# out = bar(1,c=3,b=2)
c = 3


class AClass:
  a = 1

  def __init__(self, b):
    self.b = c

  def get_b(self):
    return self.b


a = AClass(1)
#
# b = a.get_b()
# c = b + 2
#
# if b > 4:
#   d = 1
# else:
#   d = 'boo'