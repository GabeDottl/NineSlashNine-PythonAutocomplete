# import attr


class Node:

  def __init__(self):
    self.children = {}
    self.count = 0
    self.highest_child_count = 0
    self.highest_child_char = ''
    self.remainder = ''

  def increment_count(self):
    self.count += 1

  def handle_child_increase(self, char):
    if self.highest_child_char == char:
      return
    child = self.children[char]
    child_max_count = child.get_max_count_at_or_beneath()
    if child_max_count > self.highest_child_count:
      self.highest_child_char = char
      self.highest_child_count = child_max_count

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

  def traverse(self, array=False, nodes=None, path=''):
    class LoopException(Exception):
      pass

    char = ''
    try:
      if nodes is None:
        nodes = set()

      nodes.add(self)
      for char, child in self.children.items():
        if child.count > 0:
          yield child.count, [char, child.remainder] if array else char + child.remainder
        if child in nodes:
          raise LoopException(char)
        for count, arr in child.traverse(array=True, nodes=nodes, path=path + char):
          yield count, [char, child.remainder] + arr if array else ''.join([char, child.remainder] + arr)
    except LoopException as e:
      raise LoopException(''.join(e.args + [char]))
    except RecursionError as e:
      print(path)
      raise e
    nodes.remove(self)

  def to_str(self, indent=''):
    return ''.join(f'{indent}{c}{node.remainder}\n{node.to_str(indent + " "*(1+len(node.remainder)))}'
                   for c, node in self.children.items())

  def add_child(self, char, child):
    assert child != self, char
    child_max_count = child.get_max_count_at_or_beneath()
    if self.highest_child_count < child_max_count:
      self.highest_child_count = child_max_count
      self.highest_child_char = char
    self.children[char] = child

  def get_path_to(self, s):
    path = []
    curr_node = self
    sub_str = s
    while True:
      if sub_str == curr_node.remainder:
        return path
      i = min(len(curr_node.remainder), len(sub_str))
      if i > 0 and sub_str[:i] != curr_node.remainder[:i]:
        return None
      if i == len(sub_str):
        return path
      try:
        curr_node = curr_node.children[sub_str[i]]
        path.append((sub_str[i], curr_node))
        sub_str = sub_str[i+1:]
      except KeyError:

        return None

  def get_max_path(self):
    curr_node = self
    chars = []
    while curr_node.count < curr_node.highest_child_count:
      chars.append(curr_node.highest_child_char)
    return ''.join(chars)

  def assert_valid(self):
    if self in self.children:
      return False
    for child in self.children.values():
      return child.assert_valid()
    return True

class AutocompleteTrie:

  def __init__(self):
    self.root = Node()

  def prune_infrequent_copy(self, min_count):
    out = AutocompleteTrie()
    out.root = self.root.prune_infrequent_copy(min_count)
    return out

# first:
#   curr node has no remainder matching or matching child
#     create child with first letter + remainder
# next:
#   partial overlap in remainder:
#     Find split point
#     Replace node with 3:
#       1) [0:split-point]
#       2) [split_point]->old_node
#       3) [split_point]->new node
# extending overlap:
#   new child with first letter + remainder
# existing:
#   increment
#
# no matching child and doesn't match remainder?
#   Can't be reached
#
# mo matching child and does match remainder
#
# Insert partially into



  def add(self, line):
    def split_node(node, split_point, additional_remainder):
      new_node = Node()
      new_node.remainder = node.remainder[:split_point]
      c = node.remainder[split_point]
      new_node.highest_child_char = c
      new_node.highest_child_count = node.get_max_count_at_or_beneath()
      new_node.children[c] = node
      node.remainder = node.remainder[split_point+1:]
      if len(additional_remainder) > 0:
        new_child = Node()
        new_child.remainder = additional_remainder[1:]
        new_child.count = 1
        new_node.add_child(additional_remainder[0], new_child)
      return new_node

    class RemainderSplitException(Exception):
      def __init__(self, split_point):
        super(RemainderSplitException, self).__init__()
        self.split_point = split_point

    curr_node = self.root
    path = []

    line_iter = iter(line)
    b = ''
    c = ''
    try:
      for c in line_iter:
        path.append((c, curr_node))
        # Reset split point in case of exception before natural reset.
        split_point = 0
        curr_node = curr_node.children[c]
        for split_point, (a, b) in enumerate(zip(curr_node.remainder, line_iter)):
          if a != b:
            raise RemainderSplitException(split_point=split_point)
      if split_point > 0 and split_point != len(curr_node.remainder) -1:
        new_subtree = split_node(curr_node, split_point+1, '')
        new_subtree.count = 1
        c, parent = path[-1]
        parent.children[c] = new_subtree
      else: # Perfect match with curr_node - increment count.
        curr_node.increment_count()
        last_node = curr_node
        x = []
        for c, n in path:
          x.append(c)
          x.append(n.remainder)
        x.append(curr_node.remainder)
        x = ''.join(x)
        for c, node in path[::-1]:
          last_node_max_count = last_node.get_max_count_at_or_beneath()
          if node.highest_child_count < last_node_max_count:
            node.highest_child_count = last_node_max_count
            node.highest_child_char = c
          else:
            # If it's not highest at this level in the tree, it won't be further
            # up.
            break
    except RemainderSplitException as e:
      # Partially in remainder. Replace curr_node in tree with new subtree.
      # No need to update highest-values.
      prefix = ''.join(x[0] for x in path)
      remainder = ''.join([b] + list(line_iter))
      c, parent = path[-1]
      parent.children[c] = split_node(curr_node, e.split_point, remainder)
    except KeyError:
      # Matches current node's remainder if any - need to add as new child.
      remaining_chars = ''.join(list(line_iter))
      new_node = Node()
      new_node.remainder = remaining_chars
      new_node.count = 1
      curr_node.add_child(c, new_node)

  def get_frequency(self, value):
    nodes = self.root.get_path_to(value)
    if not nodes:
      return 0
    return nodes[-1][1].count

  def get_best(self, prefix):
    path = self.root.get_path_to(prefix)
    if not path:
      return None

    result_arr = []
    for c, node in path:
      result_arr.append(c)
      result_arr.append(node.remainder)
    curr_node = path[-1][1]
    while curr_node.highest_child_count > curr_node.count:
      result_arr.append(curr_node.highest_child_char)
      curr_node = curr_node.children[curr_node.highest_child_char]
      result_arr.append(curr_node.remainder)
    return ''.join(result_arr)
