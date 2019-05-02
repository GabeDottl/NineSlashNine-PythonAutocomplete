from inspect import getframeinfo, stack


class NoDictImplementationError(Exception):
  ...


class UnableToReadModuleFileError(Exception):
  ...


class CellValueNotSetError(Exception):
  ...


class ParsingError(Exception):
  ...


class SourceAttributeError(Exception):
  ...


class LoadingModuleAttributeError(Exception):
  ...


class AmbiguousFuzzyValueError(Exception):
  ...


def assert_unexpected_parso(assertion, *error):
  if not assertion:
    caller = getframeinfo(stack()[1][0])
    raise ParsingError(f'"{caller.filename}", line {caller.lineno}, {str(error)}')
