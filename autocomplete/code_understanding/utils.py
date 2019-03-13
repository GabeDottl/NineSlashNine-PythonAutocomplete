import os
import webbrowser

def shorten_path(path, splitters=(os.path.sep, '_'), preserve_last=True):
  assert len(splitters) >= 1
  vals = path.split(splitters[0])
  tmp = vals if not preserve_last else vals[:-1]
  if len(splitters) > 1:
    out = splitters[0].join(
        [shorten_path(val, splitters[1:], preserve_last=False) for val in tmp])
  else:
    out = splitters[0].join(val[0] for val in tmp)
  if preserve_last:
    return splitters[0].join([out, vals[-1]])
  return out

def display_df_in_browser(df):
  tmp_path = '/tmp/tmp.html'
  with open(tmp_path, 'w+') as f:
    f.writelines(df.to_html())
  webbrowser.get('chrome').open_new_tab('file://' + tmp_path)


def type_name(obj):
  '''Returns a name for the type of |obj|.'''
  if hasattr(obj, '__name__'):
    return obj.__name__
  if hasattr(obj, '__qualname__'):
    return obj.__qualname__
  if hasattr(obj, '__class__'):
    return type_name(obj.__class__)
  return str(type(obj))
