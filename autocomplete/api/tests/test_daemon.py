from io import StringIO
import pytest
import json

from ..daemon import Daemon
from .. import command_router

@pytest.fixture
def daemon():
  return Daemon(daemon=True, input=StringIO(), output=StringIO(), error_output=StringIO())

def test_valid_input(daemon):
  request = {
    command_router.REQUEST_ID: 1,
    command_router.COMMAND_ID: 'get_capabilities'
  }
  json_request = json.dumps(request)
  daemon._input.writelines(f'{json_request}\n')
  daemon._input.seek(0)
  daemon.process_input()
  assert not daemon._error_output.getvalue()
  result = json.loads(daemon._output.getvalue())
  assert result[command_router.RESULT_CODE] == 0
  assert 'capabilities' in result

def test_bad_input(daemon):
  request = {
    command_router.REQUEST_ID: 1,
    # command_router.COMMAND_ID: 'get_capabilities'
  }
  json_request = json.dumps(request)
  daemon._input.writelines(f'{json_request}\n')
  daemon._input.seek(0)
  daemon.process_input(raise_exception=False)
  assert not daemon._output.getvalue()
  result = json.loads(daemon._error_output.getvalue())
  assert result[command_router.RESULT_CODE] == command_router.FAILED
  assert 'command_id' in result[command_router.FAILURE_REASON]
