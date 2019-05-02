from autocomplete.code_understanding.typing import symbol_index

INDEX_PATH = '/home/gabe/index.msg'


def test_build_typing_index():
  index = symbol_index.SymbolIndex()
  index.add_file('/usr/lib/python3.7/asyncio/__init__.py')
  index.add_file('/home/gabe/code/autocomplete/autocomplete/debug/tcp_echo_server.py')
  # index.add_file('/home/gabe/code/autocomplete/autocomplete/code_understanding/typing/language_objects.py')
  index.add_path(
      '/home/gabe/code/autocomplete/autocomplete/code_understanding/typing',
      ignore_init=True)
  symbol_entries = index.find_symbol('Function')
  assert len(symbol_entries) == 1
  assert symbol_entries[0].symbol_type == symbol_index.SymbolType.TYPE
  index.save(INDEX_PATH)


def test_build_full_index():
  index = symbol_index.SymbolIndex.build_index(INDEX_PATH)
  # index.add_file('/home/gabe/code/autocomplete/autocomplete/code_understanding/typing/test.py')
  # index.add_file('/usr/lib/python3/dist-packages/entrypoints.py')
  # index.add_file('/usr/lib/python3/dist-packages/six.py')
  # index.add_file('/usr/lib/python3/dist-packages/debconf.py')
  # index.add_file('/usr/lib/python3/dist-packages/distro_info.py')
  # index.add_file('/usr/lib/python3/dist-packages/distro.py')
  # index.add_file('/usr/lib/python3/dist-packages/problem_report.py')
  # index.add_file('/usr/lib/python3/dist-packages/language_support_pkgs.py')
  # index.add_file('/usr/lib/python3/dist-packages/deb822.py')
  # index.add_file('/usr/lib/python3/dist-packages/unohelper.py')
  # index.add_file('/usr/lib/python3/dist-packages/apport_python_hook.py')
  # index.add_file('/usr/lib/python3/dist-packages/uno.py')
  # index.add_file('/usr/lib/python3/dist-packages/lsb_release.py')
  # index.add_path('/usr/lib/python3/dist-packages', ignore_init=True)
  # print('Done?')
  index.save(INDEX_PATH)


def test_load_index():
  index = symbol_index.SymbolIndex().load(INDEX_PATH)


if __name__ == "__main__":
  test_build_typing_index()
  test_load_index()
  test_build_full_index()
