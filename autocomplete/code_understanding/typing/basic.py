a = 1
b = a + 2
if True:
  b = 'asdf'
else: b = True
  
def foo():
  global b
  b = 4
print(b)
foo()
print(b)
# b = NotADirectoryError()
  # def format(filenames):
  #   for i, filename in enumerate(filenames):
  #     print(f'{i}: {filename}')
