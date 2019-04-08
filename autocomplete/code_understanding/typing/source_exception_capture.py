import attr

@attr.s
class RunTimeExceptionWrapper:
  exception = attr.ib()
  cfg_node = attr.ib()


@attr.s
class CompileTimeExceptionWrapper:
  exception = attr.ib()
  parso_node = attr.ib()

@attr.s
class SourceExceptionCapturer:
  exception_wrappers = attr.ib(factory=list)
