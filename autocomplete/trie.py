'''This class encapsulates a Trie with some optimizations and persistence abilities.

Classic tries for autocomplete may include a frequency for leaf-nodes and a pointer to the
child-subtree with the highest-frequency leaf node in it.

This Trie implementation generalizes this slightly to 'comparable' objects - i.e. objects which
support >,< and ==.

Furthermore, the Trie supports saving/loading from a file using msgpack.

In exchange for some complexity, this Trie implementation is more efficient than traditional tries
by allowing nodes to contain whole strings where it is useful to do so. This is particularly
valuable when the trie would otherwise be sparse at many nodes - for example, with file-trees.
'''
import msgpack
import attr


# We set cmp=False so that attrs doesn't add an __eq__ - we want comparisons to be id-based
# when checking for recursion loops.
@attr.s(slots=True, cmp=False)
class Trie:
  children = attr.ib(factory=dict)
  value = attr.ib(0)
  highest_child_value_at_or_beneath = attr.ib(0)
  highest_child_char = attr.ib('')
  remainder = attr.ib('')

  def _serialize(self):
    args = list(attr.astuple(self, recurse=False))
    args[0] = {k: t._serialize() for k, t in args[0].items()}
    return args

  @staticmethod
  def _deserialize(args):
    args[0] = {k: Trie._deserialize(t) for k, t in args[0].items()}
    return Trie(*args)

  def save(self, filename):
    with open(filename, 'wb') as f:
      msgpack.pack(self._serialize(), f, use_bin_type=True)

  @staticmethod
  def load(filename):
    with open(filename, 'rb') as f:
      return Trie._deserialize(msgpack.unpack(f, raw=False, use_list=True))

  def handle_child_increase(self, char):
    if self.highest_child_char == char:
      return
    child = self.children[char]
    child_max_value = child._get_max_value_at_or_beneath()
    if child_max_value > self.highest_child_value_at_or_beneath:
      self.highest_child_char = char
      self.highest_child_value_at_or_beneath = child_max_value

  def _get_max_value_at_or_beneath(self):
    return max(self.value, self.highest_child_value_at_or_beneath)

  def copy_with_lower_values_pruned(self, min_value) -> 'Trie':
    out = Trie()
    if self.highest_child_value_at_or_beneath >= min_value:
      out.highest_child_value_at_or_beneath = self.highest_child_value_at_or_beneath
      out.highest_child_char = self.highest_child_char
    for char, child in self.children.items():
      if child._get_max_value_at_or_beneath() >= min_value:
        out.children[char] = child.copy_with_lower_values_pruned(min_value)
    return out

  def traverse(self, array=False, nodes=None, path=''):
    class LoopException(Exception):
      ...

    char = ''
    try:
      if nodes is None:
        nodes = set()

      nodes.add(self)
      for char, child in self.children.items():
        if child.value > 0:
          yield child.value, [char, child.remainder] if array else char + child.remainder
        if child in nodes:
          raise LoopException(char)
        for value, arr in child.traverse(array=True, nodes=nodes, path=path + char):
          yield value, [char, child.remainder] + arr if array else ''.join([char, child.remainder] + arr)
    except LoopException as e:
      raise LoopException(''.join(e.args + [char]))
    except RecursionError as e:
      print(path)
      raise e
    nodes.remove(self)

  def to_str(self, indent=''):
    return ''.join(
        f'{indent}{c}{node.remainder} ({str(node.value)})\n{node.to_str(indent + " "*(1+len(node.remainder)+ 2 + len(str(self.value))))}'
        for c, node in self.children.items())

  def __str__(self):
    return self.to_str()

  def add_child(self, char, child):
    assert child != self, char
    child_max_value = child._get_max_value_at_or_beneath()
    if self.highest_child_value_at_or_beneath < child_max_value:
      self.highest_child_value_at_or_beneath = child_max_value
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
        break
      if i == len(sub_str):
        return path
      try:
        curr_node = curr_node.children[sub_str[i]]
        path.append((sub_str[i], curr_node))
        sub_str = sub_str[i + 1:]
      except KeyError:
        break
    return None

  def get_max_path(self):
    curr_node = self
    chars = []
    while curr_node.value < curr_node.highest_child_value_at_or_beneath:
      chars.append(curr_node.highest_child_char)
    return ''.join(chars)

  def assert_valid(self):
    if self in self.children:
      return False
    for child in self.children.values():
      return child.assert_valid()
    return True


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

  def add(self, string, value, add_value=False):
    def split_node(node, split_point, additional_remainder, additional_remainder_value):
      '''Takes an existing node with some string and splits it in its remainder string.

      The original node is preserved, just with it's remainder cut and it's new-parent is returned
      (with another child beneath said parent if additional_remainder is not '').

      For example:
      node='Google'
      split_point=1 # Go
      additional_remainder = 'al' # Goal
      Alternatively, additional_remainder may be '' in which case instead of 3 nodes, there
      are now 2 with 'Go' as a new possible end-point.
      '''
      new_node = Trie()
      new_node.remainder = node.remainder[:split_point]
      c = node.remainder[split_point]
      # new_node.value = self.default_value - TODO
      new_node.add_child(c, node)
      node.remainder = node.remainder[split_point + 1:]
      if len(additional_remainder) > 0:
        new_child = Trie()
        new_child.remainder = additional_remainder[1:]  # First char used for indexing below.
        new_child.value = additional_remainder_value
        new_node.add_child(additional_remainder[0], new_child)
        if additional_remainder_value > node._get_max_value_at_or_beneath():
          new_node.highest_child_value_at_or_beneath = additional_remainder_value
          new_node.highest_child_char = additional_remainder[0]

      if not new_node.highest_child_char:  # No remainder or remainder value's smaller.
        new_node.highest_child_value_at_or_beneath = node._get_max_value_at_or_beneath()
        new_node.highest_child_char = c

      return new_node

    class RemainderSplitException(Exception):
      def __init__(self, split_point):
        super(RemainderSplitException, self).__init__()
        self.split_point = split_point

    curr_node = self
    path = []

    string_iter = iter(string)
    b = ''
    c = ''
    try:
      for c in string_iter:
        path.append((c, curr_node))
        # Reset split point in case of exception before natural reset.
        split_point = 0
        curr_node = curr_node.children[c]
        for split_point, (a, b) in enumerate(zip(curr_node.remainder, string_iter)):
          if a != b:
            raise RemainderSplitException(split_point=split_point)
      if split_point > 0 and split_point != len(curr_node.remainder) - 1:
        new_subtree = split_node(curr_node, split_point + 1, '', 0)  # TODO: self.default_value
        new_subtree.value = value
        c, parent = path[-1]
        parent.children[c] = new_subtree
      else:  # Perfect match with curr_node - increment value.
        curr_node.value = value if not add_value else curr_node.value + value
        last_node = curr_node
        x = []
        for c, n in path:
          x.append(c)
          x.append(n.remainder)
        x.append(curr_node.remainder)
        x = ''.join(x)
        for c, node in path[::-1]:
          last_node_max_value = last_node._get_max_value_at_or_beneath()
          if node.highest_child_value_at_or_beneath < last_node_max_value:
            node.highest_child_value_at_or_beneath = last_node_max_value
            node.highest_child_char = c
          else:
            # If it's not highest at this level in the tree, it won't be further
            # up.
            break
    except RemainderSplitException as e:
      # Partially in remainder. Replace curr_node in tree with new subtree. curr_node will split
      # into 3 nodes.
      # TODO: update highest-values.
      prefix = ''.join(x[0] for x in path)
      remainder = ''.join([b] + list(string_iter))
      c, parent = path[-1]
      new_node = parent.children[c] = split_node(curr_node, e.split_point, remainder, value)
      if value > curr_node._get_max_value_at_or_beneath():
        # Need to update hierarchy.
        for c, node in path[::-1]:
          if node.highest_child_value_at_or_beneath < value:
            node.highest_child_value_at_or_beneath = value
            node.highest_child_char = c
          else:
            break  # Everything above is greater.
    except KeyError:
      # Matches current node's remainder if any - need to add as new child.
      remaining_chars = ''.join(list(string_iter))
      new_node = Trie()
      new_node.remainder = remaining_chars
      new_node.value = value
      old_max = curr_node._get_max_value_at_or_beneath()
      curr_node.add_child(c, new_node)
      if old_max < value:
        # Need to update hierarchy.
        for c, node in path[::-1][1:]:
          if node.highest_child_value_at_or_beneath < value:
            node.highest_child_value_at_or_beneath = value
            node.highest_child_char = c
          else:
            break  # Everything above is greater.

  def get_value_for_string(self, string):
    nodes = self.get_path_to(string)
    if not nodes:
      return 0
    return nodes[-1][1].value

  def get_max_value_at_or_beneath_prefix(self, prefix, default=0):
    path = self.get_path_to(prefix)
    if not path:
      return default
    return path[-1][1].highest_child_value_at_or_beneath

  def get_max(self, prefix):
    path = self.get_path_to(prefix)
    if not path:
      return None

    result_arr = []
    for c, node in path:
      result_arr.append(c)
      result_arr.append(node.remainder)
    curr_node = path[-1][1]
    while curr_node.highest_child_value_at_or_beneath > curr_node.value:
      result_arr.append(curr_node.highest_child_char)
      curr_node = curr_node.children[curr_node.highest_child_char]
      result_arr.append(curr_node.remainder)
    return ''.join(result_arr)
