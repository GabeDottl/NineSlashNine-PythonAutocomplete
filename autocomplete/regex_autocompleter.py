import re
import glob
from autocomplete.nsn_logging import *
from time import time
import os
import tensorflow as tf

def wildcard_wrapper(s):
  return '.*' + '.*'.join(list(s)) +'.*'

class SimpleRegexAutocompleter:
  def __init__(self, path):
    start = time()
    paths = glob.glob(os.path.join(path, '*py'))
    self.complete_corpus = ''
    for path in paths:
      with open(path) as f:
        self.complete_corpus += ''.join(f.readlines())
    info(f'Took {(time() - start)}s to read files')

  def search(self, s):
    wildcard_s = wildcard_wrapper(s)
    # print(wildcard_s)
    tf.data.TextLineDataset()
    return re.findall(wildcard_s, self.complete_corpus)
