#
#
# a = 1
# b = a + 2
# if True:
#   b = 'asdf'
# else:
#   a = 3

# def bar(b, a=1, *args, **kwargs):
#   a = 2
#   return 1 + a
#
# b = bar(3)
#
# bar()

def bar(a, b, c):
  return a * (b - c)

out = bar(1,c=3,b=2)
c = 3

class AClass:
  a = 1
  def __init__(self, b):
    self.b = c

  def get_b(self):
    return self.b

c = 3

a = AClass(1)

b = a.get_b()
#
# if __name__ == '__main__':
#   a = 'str'
#   print(a)




# if bar():
#   a = 'a'



# else:
#   b = True
# #
# def foo():
#   global b
#   b = 4
# print(b)
# foo()
# print(b)
# b = NotADirectoryError()
# def format(filenames):
#   for i, filename in enumerate(filenames):
#     print(f'{i}: {filename}')
