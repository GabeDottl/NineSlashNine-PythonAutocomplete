import functools

import attr


@attr.s
class Boo:
  from .storage_example import Klazz
  a = 1
