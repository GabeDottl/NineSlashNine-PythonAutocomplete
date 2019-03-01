import pkgutil
import os
import inspect
def append_func_to_tmp(func):
  import inspect
  source = inspect.getsource(func)
  tmp_py = os.path.join(os.getenv('CODE'), 'autocomplete/code_understanding/tmp.py')
  with open(tmp_py, 'a+') as f:
    f.writelines(''.join(('\n\n', source)))
