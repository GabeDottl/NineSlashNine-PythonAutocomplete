import attr


@attr.s(slots=True)
class RunTimeExceptionWrapper:
  exception = attr.ib()
  cfg_node = attr.ib()


@attr.s(slots=True)
class CompileTimeExceptionWrapper:
  exception = attr.ib()
  parso_node = attr.ib()


@attr.s(slots=True)
class SourceExceptionCapturer:
  exception_wrappers = attr.ib(factory=list)
