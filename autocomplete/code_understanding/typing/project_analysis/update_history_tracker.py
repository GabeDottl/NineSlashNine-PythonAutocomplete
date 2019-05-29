import os

import attr
import pandas as pd


@attr.s
class UpdateHistoryTracker:
  tracking_file = attr.ib()
  df = attr.ib()

  def save(self):
    if not self.df.empty:
      self.df.to_csv(self.tracking_file, index=False)

  @staticmethod
  def load(filepath, lazy_create=True) -> 'FileHistoryTracker':
    if not os.path.exists(filepath):
      if not lazy_create:
        raise ValueError(f'Invalid path for loading: {filepath}')
      else:
        df = pd.DataFrame(columns=['timestamp', 'action_type', 'data', 'filename'])
        return UpdateHistoryTracker(filepath, df)

    df = pd.read_csv(filepath)
    return UpdateHistoryTracker(filepath, df)

  def add_action(self, timestamp, action_type, data, filename):
    s = pd.Series({'timestamp': timestamp, 'action_type': action_type, 'data': data, 'filename': filename})
    self.df = self.df.append(s, ignore_index=True)
