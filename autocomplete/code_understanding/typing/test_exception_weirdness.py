class ParsingError(Exception):
  ...


def boo():
  raise ParsingError()


class X:

  def foo(self):
    raise ParsingError()

  def bar(self):
    try:
      boo()

  #   getattr(self, 'foo')()
    except ParsingError:
      print('test')


x = X()
x.bar()