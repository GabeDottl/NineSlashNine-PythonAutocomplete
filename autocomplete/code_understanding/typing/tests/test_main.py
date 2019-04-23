'''This module performs a mostly comprehensive test of the typing package.'''
import os
from glob import glob

import parso

from autocomplete.code_understanding.typing import (control_flow_graph,
                                                    module_loader)
# from autocomplete.code_understanding.typing.api import modulefrom_source
from autocomplete.code_understanding.typing.language_objects import (Function,
                                                                     Instance,
                                                                     Klass,
                                                                     Module)
from autocomplete.code_understanding.typing.pobjects import FuzzyBoolean
from autocomplete.nsn_logging import debug


def test_simple_assignment():
  source = 'a=1'
  module = module_loader.load_module_from_source(source)
  assert module['a'].value() == 1


def test_imports():
  source = '''
import numpy
import os as whatever
import hob.dob as blob
from functools import wraps
from a.b import c
from x.y.z import (q, r as s)'''
  module = module_loader.load_module_from_source(source)
  assert 'numpy' in module and isinstance(module['numpy'].value(), Module)
  assert module['numpy'].value().path() == 'numpy'
  assert 'whatever' in module and isinstance(module['whatever'].value(), Module)
  assert module['whatever'].value().path() == 'os'
  assert 'blob' in module and isinstance(module['blob'].value(), Module)
  assert module['blob'].value().path() == 'hob.dob'
  assert 'wraps' in module
  assert module['wraps'].value().name == 'functools.wraps'
  assert 'c' in module
  assert module['c'].name == 'a.b.c'
  assert 'q' in module
  assert module['q'].name == 'x.y.z.q'
  assert 's' in module
  assert module['s'].name == 'x.y.z.r'


def test_classes():
  source = '''
class X:
  b = 1
w = X()  # 0 at end
x = w  # 0 at end
y = X()  # 1 at end
X.b = 2
z = X()  # 2 at end
x.b = 0
'''
  module = module_loader.load_module_from_source(source)
  assert 'X' in module
  X = module['X'].value()
  isinstance(X, Klass)
  assert 'b' in X
  assert X['b'].value() == 2

  w = module['w'].value()
  assert w['b'].value() == 0
  x = module['x'].value()
  assert x['b'].value() == 0
  y = module['y'].value()
  assert isinstance(y, Instance)
  assert y['b'].value() == 1
  z = module['z'].value()
  assert z['b'].value() == 2


def test_stubs():
  source = '''
class X:
  b: int = ...
  def foo(a:str, other: 'x') -> int: ...

x = X()
a = x.foo(0, None)
'''
  module = module_loader.load_module_from_source(source)
  assert 'X' in module
  x = module['X'].value()
  isinstance(x, Klass)
  assert 'b' in x
  # assert 'X.b' in module  # todo
  # TODO.
  # assert module['X.b'].
  # assert module['w.b'].value() == 0
  # assert module['x.b'].value() == 0
  # assert module['y.b'].value() == 1
  # assert module['z.b'].value() == 2


def test_arrays():
  source = '''
a = [0,1,2]
b  = a[0]
c = a[23]
d = c[0]
class X: pass
x = X()
y = x[0]
a2 = 'test'
b2 = a2[0]
'''
  # TODO: a = a[0]
  module = module_loader.load_module_from_source(source)
  assert 'a' in module and isinstance(module['a'].value(), list)
  assert 'b' in module
  assert module['b'].value() == 0
  # assert module['w.b'].value() == 0
  # assert module['x.b'].value() == 0
  # assert module['y.b'].value() == 1
  # assert module['z.b'].value() == 2


def generate_test_from_actual(a_frame):
  for name, val in a_frame.locals.items():
    print(type(val.value()))
    if isinstance(val.value(), Instance):
      print(f'inst = a_frame[\'{name}\'].value()')
      print(f'assert isinstance(inst, Instance)')
    elif isinstance(val.value(), Klass):
      print(f'cls = a_frame[\'{name}\'].value()')
      print('assert isinstance(cls, Klass)')
      klass = val.value()
      for member_name in klass.keys():
        print(f'assert {member_name} in cls.members')
    elif isinstance(val.value(), Function):
      print(f'assert isinstance(a_frame[\'{name}\'].value(), Function)')
    else:
      print(f'assert a_frame[\'{name}\'].value() == {val.value()}')


def test_processing_all_typing_dir():
  typing_dir = os.path.join(os.path.dirname(__file__), '..')
  filenames = glob(os.path.join(typing_dir, '*.py'), recursive=True)
  for filename in filenames:
    debug(f'filename: {filename}')
    if os.path.basename(filename) == 'grammar.py':
      debug(f'Skipping {filename}')
      continue
    name = os.path.splitext(os.path.basename(filename))[0]
    module_loader.get_module_from_filename(name, filename)


if __name__ == '__main__':
  test_simple_assignment()
  test_stubs()
  test_classes()
  test_arrays()
  test_imports()
  test_processing_all_typing_dir()
