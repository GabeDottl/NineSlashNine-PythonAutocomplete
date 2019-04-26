import sys
from functools import wraps


def instance_memoize(func):

  @wraps(func)
  def _wrapper(self):
    memoized_name = f'_{func.__name__}_memoized'
    if hasattr(self, memoized_name):
      return getattr(self, memoized_name)
    out = func(self)
    setattr(self, memoized_name, out)
    return out

  return _wrapper


def print_tree(node, indent='', file=sys.stdout):
  print(f'{indent}{node.type}', file=file)
  if hasattr(node, 'children'):
    for c in node.children:
      print_tree(c, indent + '  ', file=file)
