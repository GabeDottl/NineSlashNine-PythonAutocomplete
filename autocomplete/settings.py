import os
from functools import wraps

def lazy_makedirs(func):
  @wraps(func)
  def wrapper(*args, **kwargs):
    path = func(*args, **kwargs)
    if not os.path.exists(path):
      os.makedirs(path)
    return path
  return wrapper

@lazy_makedirs
def get_index_dir():
  return os.path.join(os.getenv('HOME'), '.nsn')

@lazy_makedirs
def get_log_dir():
  return os.path.join(os.getenv('HOME'), '.nsn', 'logs')
  