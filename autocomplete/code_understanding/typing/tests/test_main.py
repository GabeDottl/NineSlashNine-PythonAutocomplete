'''This module performs a mostly comprehensive test of the typing package.'''
import parso

from autocomplete.code_understanding.typing import control_flow_graph
from autocomplete.code_understanding.typing.language_objects import (
    Function, Instance, Klass, Module)
from autocomplete.code_understanding.typing.api import frame_from_source


def test_simple_assignment():
  source = 'a=1'
  frame_ = frame_from_source(source)
  assert frame_['a'].value() == 1


def test_imports():
  source = '''
import numpy
import os as whatever
import hob.dob as blob
from functools import wraps
from a.b import c
from x.y.z import (q, r as s)'''
  frame_ = frame_from_source(source)
  assert 'numpy' in frame_ and isinstance(frame_['numpy'].value(), Module)
  assert frame_['numpy'].value().path == 'numpy'
  assert 'whatever' in frame_ and isinstance(frame_['whatever'].value(), Module)
  assert frame_['whatever'].value().path == 'os'
  assert 'blob' in frame_ and isinstance(frame_['blob'].value(), Module)
  assert frame_['blob'].value().path == 'hob.dob'
  assert 'wraps' in frame_
  assert frame_['wraps'].value().name == 'functools.wraps'
  assert 'c' in frame_
  assert frame_['c'].value().name == 'a.b.c'
  assert 'q' in frame_
  assert frame_['q'].value().name == 'x.y.z.q'
  assert 's' in frame_
  assert frame_['s'].value().name == 'x.y.z.r'


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
  frame_ = frame_from_source(source)
  assert 'X' in frame_ and isinstance(frame_['X'].value(), Klass)
  assert 'X.b' in frame_
  assert frame_['X.b'].value() == 2
  assert frame_['w.b'].value() == 0
  assert frame_['x.b'].value() == 0
  assert frame_['y.b'].value() == 1
  assert frame_['z.b'].value() == 2


def test_stubs():
  source = '''
class X:
  b: int = ...
  def foo(a:str, other: 'x') -> int: ...

x = X()
a = x.foo(0, None)
'''
  frame_ = frame_from_source(source)
  assert 'X' in frame_ and isinstance(frame_['X'].value(), Klass)
  assert 'X.b' in frame_
  assert frame_['X.b'].value_type() == int
  assert frame_['w.b'].value() == 0
  assert frame_['x.b'].value() == 0
  assert frame_['y.b'].value() == 1
  assert frame_['z.b'].value() == 2


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
  frame_ = frame_from_source(source)
  assert 'a' in frame_ and isinstance(frame_['a'].value(), list)
  assert 'b' in frame_
  assert frame_['b'].value() == 0
  # assert frame_['w.b'].value() == 0
  # assert frame_['x.b'].value() == 0
  # assert frame_['y.b'].value() == 1
  # assert frame_['z.b'].value() == 2


# def test_main_sample():
#    with open('/Users/gabe/code/autocomplete/autocomplete/code_understanding/typing/examples/test_main_sample_code.py') as f:
#      basic_source = ''.join(f.readlines())
#    frame_ = frame_from_source(basic_source)


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
      for member_name in klass.members.keys():
        print(f'assert {member_name} in cls.members')
    elif isinstance(val.value(), Function):
      print(f'assert isinstance(a_frame[\'{name}\'].value(), Function)')
    else:
      print(f'assert a_frame[\'{name}\'].value() == {val.value()}')


if __name__ == '__main__':
  test_simple_assignment()
  test_imports()
  test_classes()
  test_arrays()
  # test_main_sample()
