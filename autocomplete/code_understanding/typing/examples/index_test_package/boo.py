import functools
# import pandas as pd

import attr
import attr as at
from attr import ib as attrib


@attr.s
class Boo:
  from .storage_example import Klazz
  a = 1