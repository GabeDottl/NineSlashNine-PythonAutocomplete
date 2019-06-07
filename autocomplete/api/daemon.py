'''Daemon for running NSN Code Assistant.

TODO: Add support for running in a mode which listens on a port instead of stdin.

This is strongly based on ImportMagicDaemon (MIT License).
https://github.com/pilat/vscode-importmagic/
'''
import attr
import os
import sys
import io
import json
import sys
import traceback

from functools import partial

from . import command_router
from .. import nsn_logging

# Disable logging since we're using stdout as our API to listeners.
nsn_logging.send_logs_to_nowhere()

def _create_input():
  return io.open(sys.stdin.fileno(), encoding='utf-8')

@attr.s
class Daemon:
  _daemon = attr.ib()
  _input = attr.ib(factory=_create_input)
  _output = attr.ib(sys.stdout)
  _error_output = attr.ib(sys.stderr)
  _command_router = attr.ib(factory=command_router.CommandRouter)

  def _process_request(self, request):
    if not request[command_router.REQUEST_ID]:
      raise ValueError('Empty request id')

    command_id = request.get(command_router.COMMAND_ID)
    cmd = self._command_router.get_handler(command_id)
    if not cmd:
      raise ValueError('Invalid command_id')
    result = cmd(**request)
    return result if isinstance(result, dict) else dict(success=True)

  def _error_response(self, **response):
    self._error_output.write(json.dumps(response))
    self._error_output.write('\n')
    self._error_output.flush()

  def _success_response(self, **response):
    self._output.write(json.dumps(response))
    self._output.write('\n')
    self._output.flush()

  def process_input(self, raise_exception=True):
    request_id = -1
    try:
      request = json.loads(self._input.readline())
      request_id = request.get(command_router.REQUEST_ID)
      response = self._process_request(request)
      json_message = dict(id=request_id, **response)
      self._success_response(**json_message)
    except:
      exc_type, exc_value, exc_tb = sys.exc_info()
      tb_info = traceback.extract_tb(exc_tb)
      json_message = dict(id=request_id,
                          result_code=command_router.FAILED,
                          failure_reason=str(exc_value),
                          traceback=str(tb_info),
                          type=str(exc_type))
      self._error_response(**json_message)
      if raise_exception:
        raise

  def watch(self):
    while True:
      try:
        self.process_input()
      except:
        if not self._daemon:
          break


if __name__ == '__main__':
  # Extension starts the daemon with -d
  Daemon('-d' in sys.argv).watch()
