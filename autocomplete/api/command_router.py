import attr
import os

from functools import partial, wraps

from ..code_understanding.typing.project_analysis import fix_code
from ..code_understanding.typing import symbol_index
from .. import settings
from ..nsn_logging import info

RESULT_CODE = 'result_code'
SUCCESS = 0
FAILED = 1
# TODO: message? Might be more common...
FAILURE_REASON = 'failure_reason'
REQUEST_ID = 'request_id'
COMMAND_ID = 'command_id'


def return_error_on_exception(func):
  @wraps(func)
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except Exception as e:
      info(f'e: {e}')
      # raise e
      return {REQUEST_ID: kwargs[REQUEST_ID], RESULT_CODE: FAILED, FAILURE_REASON: str(e)}

  return wrapper


@attr.s
class CommandRouter:
  index = attr.ib(factory=partial(symbol_index.SymbolIndex.load, settings.get_index_dir()))

  def get_handler(self, command_id: str):
    func_name = f'handle_{command_id}'
    if hasattr(self, func_name):
      return getattr(self, func_name)
    return self.handle_bad_command

  def handle_bad_command(self, command_id, *args, **kwargs):
    return {RESULT_CODE: FAILED, FAILURE_REASON: f'"{command_id}"" is not a valid command_id.'}

  @return_error_on_exception
  def handle_get_capabilities(self, request_id, command_id):
    return {
        REQUEST_ID: request_id,
        RESULT_CODE: SUCCESS,
        'capabilities': {
            # TODO: Include types.
            'fix_code_in_file': {
                'version': 0.1,
                'inputs': ['source', 'filename'],
                'outputs': ['replacements', 'insertions', 'deletions']
            },
            'get_capabilities': {
                'version': 0.1,
                # TODO: Support for older-versions - API level in here?:
                'inputs': [],
                'outputs': ['capabilities']
            }
        }
    }

  @return_error_on_exception
  def handle_fix_code_in_file(self, request_id, source, filename, command_id):
    # Note: **kwargs so we can pass raw dict.
    assert os.path.exists(filename)
    replacements, inserts, deletions = fix_code.generate_fixes_for_missing_symbols_in_source(
        source, filename=filename, index=self.index, remove_extra_imports=True)
    return {
        REQUEST_ID: request_id,
        RESULT_CODE: SUCCESS,
        'replacements': replacements,
        'inserts': inserts,
        'deletions': deletions
    }
