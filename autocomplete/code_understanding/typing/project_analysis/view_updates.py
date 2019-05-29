import pandas as pd
import webbrowser
import os


def view():
  df = pd.read_csv(os.path.join(os.getenv('HOME'), 'fix_code_updates.csv'))
  df['filename'] = df['filename'].apply(os.path.basename)
  df.to_html('/tmp/tmp.html')
  webbrowser.open_new_tab('file:///tmp/tmp.html')


if __name__ == "__main__":
  view()
