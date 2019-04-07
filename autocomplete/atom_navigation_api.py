import os
import sys
import traceback


def goto(filename, lineno):
  os.system(f'atom {filename}:{lineno}')

def goto_exception(index=-1, tb=None):
  l = traceback.extract_tb(tb if tb else sys.last_traceback)
  goto(l[index].filename, l[index].lineno)


