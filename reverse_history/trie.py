import attr


class Node:

  def __init__(self):
    self.children = {}
    self.count = 0
    self.highest_child_count = 0
    self.highest_child_char = ''

  def increment_count(self):
    self.count += 1

  def handle_child_increase(self, char):
    if self.highest_child_char == char:
      return
    child = self.children[char]
    child_max_count = child.get_max_count_at_or_beneath()
    if child_max_count > self.highest_child_count:
      self.highest_child_char = char
      self.highest_child_count =child_max_count

  def get_max_count_at_or_beneath(self):
    return max(self.count, self.highest_child_count)

  def prune_infrequent_copy(self, min_count):
    out = Node()
    if self.highest_child_count >= min_count:
      out.highest_child_count = self.highest_child_count
      out.highest_child_char = self.highest_child_char
    for char, child in self.children.items():
      if child.get_max_count_at_or_beneath() >= min_count:
        out.children[char] = child.prune_infrequent_copy(min_count)
    return out

  def traverse(self, array=False):
    for char, child in self.children.items():
      if child.count > 0:
        yield child.count, [char] if array else char
      for count, arr in child.traverse(array=True):
        yield count, [char] + arr if array else ''.join([char] + arr)


  def to_str(self, indent=''):
    return ''.join(f'{indent}{c}\n{node.to_str(indent + " ")}'
                   for c, node in self.children.items())

  def add_child(self, char, child):
    child_max_count = child.get_max_count_at_or_beneath()
    if self.highest_child_count < child_max_count:
      # print(f'{len(self.children)}: {child.highest_child_count} vs {self.highest_child_count}')
      self.highest_child_count = child_max_count
      self.highest_child_char = char
    self.children[char] = child

  def get_descendant_node(self, s):
    if len(s) == 0:
      return self
    try:
      return self.children[s[0]].get_descendant_node(s[1:])
    except KeyError:
      return None

  def get_max_path(self):
    curr_node = self
    chars = []
    while curr_node.count < curr_node.highest_child_count:
      chars.append(curr_node.highest_child_char)
    return ''.join(chars)

class AutocompleteTrie:

  def __init__(self):
    self.root = Node()

  def prune_infrequent_copy(self, min_count):
    out = AutocompleteTrie()
    out.root = self.root.prune_infrequent_copy(min_count)
    return out

  def add(self, line):
    curr_node = self.root
    path = []
    try:
      for i, c in enumerate(line):
        path.append(curr_node)
        curr_node = curr_node.children[c]
    except KeyError:
      remaining_chars = line[i:]
      child = Node()
      child.count = 1
      for c in remaining_chars[:0:-1]: # Reverse search without first char.
        parent = Node()
        parent.add_child(c, child)
        child = parent
        path.append(curr_node)
      path[-1].add_child(remaining_chars[0], child)
      return
    # Current node perfectly matches line - make sure it's a leaf and increase
    # its reference count.
    curr_node.increment_count()
    last_node = curr_node
    for c, node in zip(line[::-1], path[::-1]):
      last_node_max_count = last_node.get_max_count_at_or_beneath()
      if node.highest_child_count < last_node_max_count:
        node.highest_child_count = last_node_max_count
        node.highest_child_char = c
      else:
        break


  def get_frequency(self, value):
    curr_node = self.root
    try:
      for i, c in enumerate(value):
        curr_node = curr_node.children[c]
    except KeyError:
      # Doesn't match nothing. Try/except faster than branching.
      return None
    return curr_node.count

  def get_best(self, prefix):
    curr_node = self.root
    try:
      for i, c in enumerate(prefix):
        curr_node = curr_node.children[c]
    except KeyError:
      return None

    result_arr = [prefix]
    while curr_node.highest_child_count > curr_node.count:
      result_arr.append(curr_node.highest_child_char)
      curr_node = curr_node.children[curr_node.highest_child_char]
    return ''.join(result_arr)
