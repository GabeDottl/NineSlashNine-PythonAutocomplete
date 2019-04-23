'''This module has a variety of unresolved symbols to find!'''
import Q

a = unresolved1


class B:
  b = unresolved2
  c = a
  unresolved3 = 1

  def foo(self):
    c = unresolved3  # Shouldn't pull in

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
        g = unresolved5

      boo2(1)

    boo()
    c = unresolved4
    c = self


b = B()
b.foo()
