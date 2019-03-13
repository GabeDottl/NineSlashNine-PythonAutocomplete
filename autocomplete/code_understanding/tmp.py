import inspect
import os


def append_func_to_tmp(func):
  source = inspect.getsource(func)
  tmp_py = os.path.join(os.getenv('CODE'), 'autocomplete/code_understanding/tmp.py')
  with open(tmp_py, 'a+') as f:
    f.writelines(''.join(('\n\n', source)))
