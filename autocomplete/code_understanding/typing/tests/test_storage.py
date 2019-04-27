import os

import msgpack

from autocomplete.code_understanding.typing import (
    language_objects, module_loader)
from autocomplete.code_understanding.typing.module_index import ModuleIndex


def test_store_retrieve():
  tmp_file = '/tmp/tmp.hdf'
  if os.path.exists(tmp_file):
    os.remove(tmp_file)

  index = ModuleIndex(tmp_file)
  module_name = 'autocomplete.code_understanding.typing.examples.example_storage'
  storage_example_module = module_loader.load_module(module_name)
  index.store_module(storage_example_module)
  module = index.retrieve_module(module_name)
  assert 'autocomplete' in index.file


def test_serialization_deserialization():
  p = language_objects.Parameter('a', language_objects.ParameterType.SINGLE)
  with open('/tmp/tmp.msg', 'wb') as f:
    msgpack.pack(p, f, default=language_objects.serialize, use_bin_type=True)
  with open('/tmp/tmp.msg', 'rb') as f:
    pl = language_objects.deserialize(*msgpack.unpack(f, raw=False))


if __name__ == "__main__":
  test_serialization_deserialization()
  # test_store_retrieve()
