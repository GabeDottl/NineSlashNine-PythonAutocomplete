import msgpack

from .. import module_loader, serialization
from ..utils import assert_expected_iterable

# def test_store_retrieve():
#   tmp_file = '/tmp/tmp.hdf'
#   if os.path.exists(tmp_file):
#     os.remove(tmp_file)

#   index = ModuleIndex(tmp_file)
#   module_name = 'autocomplete.code_understanding.typing.examples.example_storage'
#   storage_example_module = module_loader.get_module(module_name, lazy=False)
#   index.store_module(storage_example_module)
#   module = index.retrieve_module(module_name)
#   assert 'autocomplete' in index.file


def test_serialization_deserialization():
  module_name = 'autocomplete.code_understanding.typing.examples.index_test_package.storage_example'
  # module_name = 'autocomplete.code_understanding.typing.control_flow_graph'
  module_key = module_loader.module_key_from_name(module_name, '.')
  assert not module_key.is_bad()
  module = module_loader.get_module_from_key(module_key, lazy=False)

  with open('/tmp/tmp.msg', 'wb') as f:
    msgpack.pack(module, f, default=serialization.serialize, use_bin_type=True)
  with open('/tmp/tmp.msg', 'rb') as f:
    module_loaded = module_loader.deserialize(*msgpack.unpack(f, raw=False))
  assert_expected_iterable(module_loaded.get_members().keys(), module.get_members().keys())


if __name__ == "__main__":
  test_serialization_deserialization()
