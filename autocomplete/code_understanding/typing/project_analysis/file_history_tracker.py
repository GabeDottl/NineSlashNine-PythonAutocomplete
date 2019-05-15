import msgpack
import time
import os
import attr


@attr.s
class FileHistoryTracker:
  tracking_file = attr.ib()
  file_timestamp_dict = attr.ib(factory=dict)

  def save(self):
    with open(self.tracking_file, 'wb') as f:
      msgpack.pack(self.file_timestamp_dict, f, use_bin_type=True)

  @staticmethod
  def load(filepath, lazy_create=True) -> 'FileHistoryTracker':
    if not os.path.exists(filepath):
      if not lazy_create:
        raise ValueError(f'Invalid path for loading: {filepath}')
      else:
        return FileHistoryTracker(filepath)

    with open(filepath, 'rb') as f:
      d = msgpack.unpack(f, raw=False, use_list=False)
      return FileHistoryTracker(filepath, d)

  def update_timestamp_for_file(self, filename, timestamp=None):
    if timestamp is None:
      timestamp = time.time()
    self.file_timestamp_dict[filename] = timestamp

  def has_file_changed_since_timestamp(self, filename):
    if filename not in self.file_timestamp_dict:
      return True

    modified_timestamp = os.path.getmtime(filename)
    last_update_timestamp = self.file_timestamp_dict[filename]
    return modified_timestamp > last_update_timestamp
    # print(datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S'))