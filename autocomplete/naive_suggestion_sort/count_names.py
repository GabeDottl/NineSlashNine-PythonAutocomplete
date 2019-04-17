'''A module which does a simple count of how frequently all name tokens are used
within a given path of python files.'''
import argparse
import os
import pickle
from collections import OrderedDict, defaultdict
from glob import glob
from tokenize import NAME, tokenize

from autocomplete.nsn_logging import *


def count_names(path, verbose=True):
  filenames = glob(os.path.join(path, '**', '*.py'), recursive=True)
  name_counts = defaultdict(int)
  num_filenames = len(filenames)
  info(f'Number of files: {num_filenames}', log=verbose)
  assert num_filenames, f'{num_filenames}'
  log_period = num_filenames // 10
  percentage = 0
  for i, filename in enumerate(filenames):
    try:
      if log_period > 0 and i % log_period == 0:
        info(f'Prcocessed {percentage}% of files.', log=verbose)
        percentage += 10
      with open(filename, 'rb') as f:
        tokens = tokenize(f.readline)
        for type_, string, start, end, line in tokens:
          if type_ == NAME:
            name_counts[string] += 1
    except Exception as e:
      print(e)
      print(f'Failed to process filename: {filename}')

  info(f'Prcocessed 100% of files.')
  return name_counts


def read_saved_name_counts(path):
  with open(path, 'rb') as f:
    return pickle.load(f)


def save_name_counts(name_counts, path):
  with open(path, 'wb+') as f:
    pickle.dump(name_counts, f)


def main(path, output_filename, **kwargs):
  name_counts = count_names(path)
  name_counts = OrderedDict(sorted(name_counts.items(), key=lambda kv: -kv[1]))
  save_name_counts(name_counts, output_filename)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('path')
  parser.add_argument('output_filename')
  args = parser.parse()
  main(**args)
