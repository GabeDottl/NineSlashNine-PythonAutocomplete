import pytest
from .. import command_router
from ...nsn_logging import info


@pytest.fixture
def router():
  info(f'Called')
  return command_router.CommandRouter()


def test_fix_code(router):
  source = '1'
  fix_input = {'request_id': 0, 'command_id': 'fix_code_in_file', 'source': source, 'filename': __file__}
  handler = router.get_handler('fix_code_in_file')
  result = handler(**fix_input)
  assert result[command_router.RESULT_CODE] == command_router.SUCCESS


def test_get_capabilities(router):
  fix_input = {
      'request_id': 0,
      'command_id': 'get_capabilities',
  }
  handler = router.get_handler('get_capabilities')
  result = handler(**fix_input)
  assert result[command_router.RESULT_CODE] == command_router.SUCCESS