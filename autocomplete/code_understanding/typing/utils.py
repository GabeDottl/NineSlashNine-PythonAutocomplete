import sys
from functools import wraps
from typing import Dict


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


def to_dict_iter(obj):
  if hasattr(obj, '__dict__'):
    return obj.__dict__.items()
  elif isinstance(obj, Dict):
    return obj.items()
  elif hasattr(obj, '__slots__'):

    def iterator():
      for name in obj.__slots__:
        try:
          yield name, getattr(obj, name)
        except AttributeError:
          pass

    return iterator()

  return iter([])


def attrs_names_from_class(class_):
  for x in class_.__attrs_attrs__:
    yield x.name
