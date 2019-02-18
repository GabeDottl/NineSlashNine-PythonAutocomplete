import inspect

def get_classes(module):
  out = []
  for name, member in inspect.getmembers(module):
    if inspect.isclass(member):
      out.append(member)
  return out

def get_bucketized_members(module):
  out = {'class': [], 'function': [], 'method': [], 'module': []}

  for name, member in inspect.getmembers(module):
    if inspect.isclass(member):
      out['class'].append(member)
    elif inspect.isfunction(member):
      out['function'].append(member)
    elif inspect.ismethod(member):
      out['method'].append(member)
    elif inspect.ismodule(member):
      out['module'].append(member)
  return out
