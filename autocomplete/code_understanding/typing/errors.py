class ParsingError(Exception):
  ...


def assert_unexpected_parso(assertion, *error):
  if not assertion:
    raise ParsingError(str(error))
