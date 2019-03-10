import attr


class Node:

  def __init__(self):
    self.children = {}
    self.leaf = False
    self.count = 0
    self.highest_child_count = 0
    self.highest_child_char = ''
    self.highest_child = self
    # self.parent = None

  def increment_count(self):
    assert self.leaf
    self.count += 1
    if self.count > self.highest_child_count:
      self.highest_child_count = self.count
      self.highest_child = self

  def to_str(self, indent=''):
    return ''.join(f'{indent}{c}\n{node.to_str(indent + " ")}'
                   for c, node in self.children.items())

  def add_child(self, char, child):
    if self.highest_child_count < child.highest_child_count:
      print(f'{len(self.children)}: {child.highest_child_count} vs {self.highest_child_count}')
      self.highest_child = child
      self.highest_child_count = child.highest_child_count
      self.highest_child_char = char
    self.children[char] = child

  def get_descendant_node(self, s):
    curr_node = self
    try:
      for i, c in enumerate(s):
        curr_node = curr_node.children[c]
    except KeyError:
      return None
    return curr_node
    # child.parent = self



# class StringLeafNode(Node):
#   def __init__(self, s):
#     super(StringLeafNode, self).__init__()
#     # self.children = None
#     self.leaf = True
#     self.string = s
#     self.count = 1
#     self.highest_child = self
#     self.highest_child_count = self.count
#
#   def cut(self):
#     out = StringLeafNode(self.string[1:])
#     out.count = self.count
#     out.highest_child_count = self.count
#
#   def to_str(self, indent=''):
#     return self.string


class AutocompleteTrie:

  def __init__(self):
    self.root = Node()

  def prune_infrequent(self, min_count):
    pass

  def add(self, line):
    print(f'Adding {line}')
    curr_node = self.root
    path = []
    try:
      for i, c in enumerate(line):
        path.append(curr_node)
        curr_node = curr_node.children[c]
    except KeyError:
      remaining_chars = line[i:]
      child = Node()
      child.leaf = True
      child.count = 1
      child.highest_child_count = child.count
      for c in remaining_chars[:0:-1]:
        print(c)
        parent = Node()
        parent.add_child(c, child)
        child = parent
        path.append(curr_node)
      print(remaining_chars)
      path[-1].add_child(remaining_chars[0], child)
      return
      # new_node.leaf = True
      #
      # print(f'remaining_chars {remaining_chars}')
      # if not curr_node.leaf or not hasattr(
      #     curr_node, 'string') or curr_node.string != remaining_chars:
      #   if hasattr(curr_node, 'string'):
      #     print(f'{remaining_chars} and {curr_node.string}')
      #   if i < len(line) - 1:  # More than 1 char remaining.
      #     new_node = StringLeafNode(remaining_chars[1:])
      #   else:  # Single char.
      #     new_node = Node()
      #     new_node.leaf = True
      #     new_node.count = 1
      #     new_node.highest_child = new_node
      #     new_node.highest_child_count = new_node.count
      #   # Split StringLeafNode into inner and new leaf.
      #   if isinstance(curr_node, StringLeafNode):
      #     new_leaf = curr_node.cut()
      #     new_curr_node = Node()
      #     new_curr_node.children[curr_node.string[0]] = new_leaf
      #     # Replace curr_node with new_curr_node in tree.
      #     # print(path[-1].children)
      #     assert path[-1].children[line[i - 1]] == curr_node, (line[:i],
      #                                                          type(path[-1]))
      #     path[-1].children[c] = new_curr_node
      #     curr_node = new_curr_node
      #   print(f'Adding child letter {c} with new node {str(new_node)}')
      #   curr_node.children[c] = new_node
      #   return
    # Current node perfectly matches line - make sure it's a leaf and increase
    # its reference count.
    curr_node.leaf = True
    curr_node.increment_count()
    last_node = curr_node
    for c, node in zip(line, path[::-1]):
      if node.highest_child_count < last_node.highest_child_count:
        print('Updating counts')
        node.highest_child_count = last_node.highest_child_count
        node.highest_child = last_node.highest_child
        node.highest_child_char = c


  def get_frequency(self, value):
    curr_node = self.root
    try:
      for i, c in enumerate(prefix):
        curr_node = curr_node.children[c]
    except KeyError:
      # Doesn't match nothing. Try/except faster than branching.
      return None
    assert curr_node.string

  def get_best(self, prefix):
    curr_node = self.root
    try:
      for i, c in enumerate(prefix):
        curr_node = curr_node.children[c]
    except KeyError:
      return None
      # try:  # Found matching StringLeafNode
      #   if prefix[i:] == curr_node.string[len(prefix) - i]:
      #     return prefix[:i] + curr_node.string
      # except AttributeError:  # No string.
      #   # Doesn't match nothing. Try/except faster than branching.
      #   return None

    result_arr = [prefix]
    print(result_arr)
    print(curr_node)
    while curr_node.highest_child != curr_node:
      result_arr.append(curr_node.highest_child_char)
      curr_node = curr_node.highest_child
      print(curr_node)
    return ''.join(result_arr)
