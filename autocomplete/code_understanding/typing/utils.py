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
