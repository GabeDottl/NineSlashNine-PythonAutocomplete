"""NineSlashNine logger wrapper.

This primarily just wraps the abseil logging module with a bit of NSN-standard
components.

The rationale for doing this is a few:
* Allows some consistent customization over abseil logging.
* Allows swapping out Abseil easily across the board - e.g. for logging to disk."""
from absl import logging
import inspect

logging.set_verbosity('info')

def info(message, *args, log=True, **kwargs):
  if log:
    logging.info(message, *args, **kwargs)

def log(level, message, *args, **kwargs):
  logging.log(level, message, *args, **kwargs)

def log_freq(message, log=True):
  if log:
    logging.log_every_n_seconds(logging.INFO, 'clamped_log: %s' % message, n_seconds=5)

# Make the Abseil logging module ignore the functions in this module when
# logging line numbers and functions.
for item in dir():
  if inspect.isfunction(globals()[item]):
    logging.skip_log_prefix(item)
