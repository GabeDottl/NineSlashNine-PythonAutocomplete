import attr


@attr.s
class ModuleExports:
  imported_modules = attr.ib()  # Recursive dig into.
  classes = attr.ib()
  functions = attr.ib()
  variables = attr.ib()  # Everything else
