#
#
# a = 1
# b = a + 2
# if True:
#   b = 'asdf'
# else:
#   a = 3

def bar(b, a=1, *args, **kwargs):
  a = 2
  return 1 + a

b = bar(3)

bar()


# class AClass:
#   a = 1
#   q = 's'
#
# a = AClass()
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
