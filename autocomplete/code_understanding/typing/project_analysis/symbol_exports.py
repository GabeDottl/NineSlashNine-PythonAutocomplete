'''This module derives what symbols are exported from a given source.'''
import argparse
from argparse import ArgumentParser
from pprint import pprint

from autocomplete.code_understanding.typing import api


def extract_exports(source):
  frame_ = api.frame_from_source(source)
  exports = dict(filter(lambda k, v: '_' == k[0], frame_._locals))
  return exports


if __name__ == "__main__":
  parser = ArgumentParser()
  parser.add_argument('target')
  args, _ = parser.parse_known_args()
  with open(args.target) as f:
    source = ''.join(f.readlines())
    pprint(extract_exports(source))
