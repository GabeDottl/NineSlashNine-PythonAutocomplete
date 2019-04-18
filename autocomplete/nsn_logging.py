"""NineSlashNine logger wrapper.

This primarily just wraps the abseil logging module with a bit of NSN-standard
components.

The rationale for doing this is a few:
* Allows some consistent customization over abseil logging.
* Allows swapping out Abseil easily across the board - e.g. for logging to disk."""
import inspect

from absl import logging

logging.set_verbosity('info')


def info(message, *args, log=True, **kwargs):
  if log:
    logging.info(message, *args, **kwargs)

def debug(message, *args, log=True, **kwargs):
  if log:
    logging.info(message, *args, **kwargs)

def warning(message, *args, log=True, **kwargs):
  if log:
    logging.warning(message, *args, **kwargs)

def error(message, *args, log=True, **kwargs):
  if log:
    logging.error(message, *args, **kwargs)

def log(level, message, *args, **kwargs):
  logging.log(level, message, *args, **kwargs)


def log_freq(level, message, log=True, n_seconds=5):
  if log:
    logging.log_every_n_seconds(
        level, 'clamped_log: %s' % message, n_seconds=n_seconds)


# Make the Abseil logging module ignore the functions in this module when
# logging line numbers and functions.
for item in dir():
  if inspect.isfunction(globals()[item]):
    logging.skip_log_prefix(item)
