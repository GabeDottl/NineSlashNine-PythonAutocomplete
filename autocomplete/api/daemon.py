'''Daemon for running NSN Code Assistant. 

TODO: Add support for running in a mode which listens on a port instead of stdin.

This is strongly based on ImportMagicDaemon (MIT License).
https://github.com/pilat/vscode-importmagic/
'''
import os
import sys
import io
import json
import sys
import traceback

from . import command_router
from .. import nsn_logging

# Disable logging since we're using stdout as our API to listeners.
nsn_logging.send_logs_to_nowhere()

class Daemon(Extension):
  def __init__(self, daemon):
    self._input = io.open(sys.stdin.fileno(), encoding='utf-8')
    self._daemon = daemon
    self.command_router = command_router.CommandRouter()
    super(Daemon, self).__init__()

  def _process_request(self, request):
    action = request.get('action')
    cmd = commands.get_handler(action)
    if not cmd:
      raise ValueError('Invalid action')
    result = cmd(self, **request)
    return result if isinstance(result, dict) else dict(success=True)

  def _error_response(self, **response):
    sys.stderr.write(json.dumps(response))
    sys.stderr.write('\n')
    sys.stderr.flush()

  def _success_response(self, **response):
    sys.stdout.write(json.dumps(response))
    sys.stdout.write('\n')
    sys.stdout.flush()

  def watch(self):
    while True:
      try:
        request = json.loads(self._input.readline())
        request_id = request.get('request_id')

        if not request_id:
          raise ValueError('Empty request id')

        response = self._process_request(request)
        json_message = dict(id=request_id, **response)
        self._success_response(**json_message)
      except:
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb_info = traceback.extract_tb(exc_tb)
        json_message = dict(error=True,
                            id=request_id,
                            message=str(exc_value),
                            traceback=str(tb_info),
                            type=str(exc_type))
        self._error_response(**json_message)
        if not self._daemon:
          break


if __name__ == '__main__':
  # Extension starts the daemon with -d
  Daemon('-d' in sys.argv).watch()
