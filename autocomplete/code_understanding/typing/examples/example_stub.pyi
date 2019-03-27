# To import:
# import sys,imp
# with open('autocomplete/autocomplete/code_understanding/typing/example_stub.pyi') as f:
#   example_stub_code = ''.join(f.readlines())
# example_stub = imp.new_module('example_stub')
# exec(example_stub_code, example_stub.__dict__)

# https://docs.python.org/3/library/typing.html#typing.Union - OneOf
from typing import Union

x: int

def afunc(code: str) -> int: ...
def afunc(a: int, b: int = ...) -> int: ...

class Bar:
  a: str

  # returns_ = example_stub.Bar.foo.__annotations__['return']
  # returns_.__args__
  def foo(self) -> Union[int, str]: ...
