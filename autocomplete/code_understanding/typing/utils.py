import sys
from functools import wraps


def instance_memoize(func):
  value = None

  @wraps(func)
  def _wrapper(self):
    nonlocal value
    if value is None:
      value = func(self)
    return value

  return _wrapper


def print_tree(node, indent='', file=sys.stdout):
  print(f'{indent}{node.type}', file=file)
  if hasattr(node, 'children'):
    for c in node.children:
      print_tree(c, indent + '  ', file=file)
