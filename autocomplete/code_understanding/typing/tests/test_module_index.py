import os

from autocomplete.code_understanding.typing import module_loader
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


if __name__ == "__main__":
  test_store_retrieve()
