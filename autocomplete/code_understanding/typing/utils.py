import itertools
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


PYTHON2_EXCLUSIVE_BUILTINS = [
    'intern', 'unichr', 'StandardError', 'reduce', 'exit', 'reload', 'file',
    'execfile', 'basestring', 'long', 'apply', 'quit', 'coerce', 'raw_input',
    'cmp', 'xrange', 'unicode', 'buffer'
]


def get_possible_builtin_symbols():
  return itertools.chain(['__builtins__', '__builtin__'], __builtins__.keys(),
                         PYTHON2_EXCLUSIVE_BUILTINS)


def print_tree(node, indent='', file=sys.stdout):
  print(f'{indent}{node.type}', file=file)
  if hasattr(node, 'children'):
    for c in node.children:
      print_tree(c, indent + '  ', file=file)


def to_dict_iter(obj):
  if hasattr(obj, '__dict__'):
    return obj.__dict__.items()
  elif isinstance(obj, dict):
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
