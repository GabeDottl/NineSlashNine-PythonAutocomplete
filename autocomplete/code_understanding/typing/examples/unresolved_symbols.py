'''This module has a variety of unresolved symbols to find!'''
import Q

a = 2  # unresolved1


class B:
  b = 2  # unresolved2
  c = a
  unresolved3 = 1

  def foo(self):
    c = 2  # unresolved3  # Shouldn't pull in

    def boo():
      d = c
      e = d
      e = a
      f = Q

      def boo2(s):
        g = d
        g = self.unresolved3
        g = a
        with open('f') as file:
          source = ''.join(file.readlines())
        for number in range(10):
          print(source)
          print(number)
        while True:
          h = 2
        print(h)
        print(number)
        print(source)
        f = file
        g = 2
        unresolved4 = 1
        g = 2  # unresolved5

      boo2(1)

    boo()
    c = 2  # unresolved4
    c = self


b = B()
b.foo()
