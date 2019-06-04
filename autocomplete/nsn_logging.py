"""NineSlashNine logger wrapper.

This primarily just wraps the logging module with a bit of NSN-standard components.

The rationale for doing this is a few:
* Allows some consistent customization.
* Allows changing logging-routing across the board - e.g. for logging to disk.
* Simpler API to work with.
"""
import os
import inspect

import logging
import logging.handlers
from . import settings

# import coloredlogs
# coloredlogs.install()

_logger = logging.getLogger('__default__')
_formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
_handler = None
_context_list = []
_context_prefix = 'a'

_logging_disabled = False


def set_verbosity(level):
  if level == 'info':
    _logger.setLevel(logging.INFO)
  elif level == 'debug':
    _logger.setLevel(logging.DEBUG)
  elif level == 'error':
    _logger.setLevel(logging.ERROR)


# TODO: contextmanager.
def push_context(value):
  _context_list.append(value)
  _context_prefix = '|'.join(_context_list)


def pop_context():
  _context_list.pop()
  _context_prefix = '|'.join(_context_list)


def info(message, *args, log=True, **kwargs):
  if log and not _logging_disabled:
    _logger.info(_format_message(message), *args, **kwargs)


def debug(message, *args, log=True, **kwargs):
  if log and not _logging_disabled:
    _logger.debug(_format_message(message), *args, **kwargs)


def warning(message, *args, log=True, **kwargs):
  if log and not _logging_disabled:
    _logger.warning(_format_message(message), *args, **kwargs)


def error(message, *args, log=True, **kwargs):
  if log and not _logging_disabled:
    _logger.error(_format_message(message), *args, **kwargs)


def _format_message(message, include_func=False):
  filename, func, lineno = __get_call_info(2)  # info for calling function.
  filename = os.path.basename(filename)
  context_str = f'{"|".join(_context_list)}:' if _context_list else ''
  if include_func:
    return f'{filename}#{func}({lineno}):{context_str} {message}'
  else:
    return f'{filename}:{lineno}:{context_str} {message}'


# TODO: send_logs_to_port. https://docs.python.org/3/howto/logging-cookbook.html#sending-and-receiving-logging-events-across-a-network


def send_logs_to_file():
  assert False, "Untested"
  global _handler, _logger
  if _handler:
    _logger.removeHandler(_handler)
  _handler = logging.handlers.RotationFileHandler()
  _handler.setFormatter(_formatter)
  _logger.addHandler(_handler)
  # _logger.get_absl_handler().python_handler.start_logging_to_file('nsn', settings.get_log_dir())


def send_logs_to_stdout():
  global _handler, _logger
  if _handler:
    _logger.removeHandler(_handler)
  _handler = logging.StreamHandler()
  _handler.setFormatter(_formatter)
  _logger.addHandler(_handler)


def send_logs_to_nowhere():
  global _logging_disabled
  _logging_disabled = True


def __get_call_info(function_lookback_count=1):
  '''function_lookback_count = 1 corresponds to the calling function.'''
  stack = inspect.stack()
  stack_level = function_lookback_count + 1  # To skip this function, add 1.
  filename = stack[stack_level][1]
  lineno = stack[stack_level][2]
  func = stack[stack_level][3]

  return filename, func, lineno


set_verbosity('info')
send_logs_to_stdout()
