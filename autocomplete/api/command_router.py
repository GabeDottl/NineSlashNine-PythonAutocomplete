import attr
import os

from functools import partial, wraps

from ..code_understanding.typing.project_analysis import fix_code
from ..code_understanding.typing import symbol_index
from .. import settings
from ..nsn_logging import info

SUCCESS = 0
FAILED = 1
RESULT_CODE = 'result_code'
REASON = 'reason'

@attr.s
class CommandRouter:
  index = attr.ib(factory=partial(symbol_index.SymbolIndex.load, settings.get_index_dir()))

  def get_handler(self, action: str):
    assert action == 'fix_code'
    return self.handle_fix_code

  def return_error_on_exception(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
      try:
        return func(*args, **kwargs)
      except Exception as e:
        info(f'e: {e}')
        raise e
        return {RESULT_CODE: FAILED, REASON: str(e)}
    return wrapper

  @return_error_on_exception
  def handle_fix_code(self, source, filename, **kwargs):
    # Note: **kwargs so we can pass raw dict.
    assert os.path.exists(filename)
    new_code, changed = fix_code.fix_missing_symbols_in_source(source,
                                                      filename=filename,
                                                      index=self.index,
                                                      remove_extra_imports=True)
    return {RESULT_CODE: SUCCESS, 'source': changed}
