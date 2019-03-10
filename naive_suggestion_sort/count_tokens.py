'''A module which does a simple count of how frequently all name tokens are used
within a given path of python files.'''
from glob import glob
from tokenize import tokenize, NAME
import os
from collections import defaultdict, OrderedDict
import argparse
import pickle
from nsn_logging import *

def count_tokens(path, verbose=True):
  filenames = glob(os.path.join(path, '**', '*.py'), recursive=True)
  word_counts = defaultdict(int)
  num_filenames = len(filenames)
  info(f'Number of files: {num_filenames}', log=verbose)
  assert num_filenames, f'{num_filenames}'
  log_period = num_filenames // 10
  percentage = 0
  for i, filename in enumerate(filenames):
    try:
      if log_period > 0 and i % log_period == 0:
        info(f'Prcocessed {percentage}% of files.', log=verbose)
        percentage +=10
      with open(filename, 'rb') as f:
        tokens = tokenize(f.readline)
        for type_, string, start, end, line in tokens:
          if type_ == NAME:
            word_counts[string] += 1
    except Exception as e:
      print(e)
      print(f'Failed to process filename: {filename}')

  info(f'Prcocessed 100% of files.')
  return word_counts

def main(path, output_filename, **kwargs):
  word_counts = count_tokens(path)
  word_counts = OrderedDict(sorted(word_counts.items(), key=lambda kv: -kv[1]))

  with open(output_filename, 'wb') as f:
    pickle.dump(word_counts, f)



if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('path')
  parser.add_argument('output_filename')
  args = parser.parse()
  main(**args)
