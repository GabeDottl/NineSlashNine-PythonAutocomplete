import attr


@attr.s(slots=True)
class ModuleExports:
  imported_modules = attr.ib()  # Recursive dig into.
  classes = attr.ib()
  functions = attr.ib()
  variables = attr.ib()  # Everything else
