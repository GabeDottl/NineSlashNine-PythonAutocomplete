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
import os


# We set cmp=False so that attrs doesn't add an __eq__ - we want comparisons to be id-based
# when checking for recursion loops.
@attr.s(slots=True, cmp=False)
class Trie:
  children = attr.ib(factory=dict)
  # IMPORTANT: See _serialize logic before adding to this. Tl;Dr: be careful with defaults & order.
  # The ordering here is trying to optimize for the _serialize function.
  end_point = attr.ib(False)
  remainder = attr.ib('')
  highest_child_value_at_or_beneath = attr.ib(0)
  highest_child_char = attr.ib('')
  value = attr.ib(0)
  store_value = attr.ib(None)

  def _serialize(self):
    args = list(attr.astuple(self, recurse=False))
    args[0] = {k: t._serialize() for k, t in args[0].items()}
    # This a clever but slightly dangerous optimization. All attributes after the first evaluate
    # to False by default - we can therefore skip saving them in these cases and save some space on
    # and increase read/write speed.
    for i in range(1, len(args) - 2):  # -2 = skip first arg.
      if args[-1 * i]:
        if i == 1:
          return args  # Need to include everything.
        else:
          return args[:-i + 1]  # Include everything but last (i-1)-attributes.
    return args[:1]  # Only self.children needs to be stored.

  @staticmethod
  def _deserialize(args):
    args[0] = {k: Trie._deserialize(t) for k, t in args[0].items()}
    return Trie(*args)

  @staticmethod
  def load(filename):
    with open(filename, 'rb') as f:
      return Trie._deserialize(msgpack.unpack(f, raw=False, use_list=True))

  def save(self, filename):
    with open(filename, 'wb') as f:
      msgpack.pack(self._serialize(), f, use_bin_type=True)

  def _get_max_value_at_or_beneath(self):
    return max(self.value, self.highest_child_value_at_or_beneath)

  def copy_with_lower_values_pruned(self, min_value) -> 'Trie':
    out = type(self)()  # Supports subclass.
    out.end_point = True
    if self.highest_child_value_at_or_beneath >= min_value:
      out.highest_child_value_at_or_beneath = self.highest_child_value_at_or_beneath
      out.highest_child_char = self.highest_child_char
    for char, child in self.children.items():
      if child._get_max_value_at_or_beneath() >= min_value:
        out.children[char] = child.copy_with_lower_values_pruned(min_value)
    return out

  def children_store_value_iter(self, first=True):
    if self.store_value and not first:
      yield self.store_value
    for child in self.children.values():
      return child.children_store_value_iter(False)

  def _to_str(self, indent=''):
    return ''.join(
        f'{indent}{c}{node.remainder} ({str(node.value)})\n{node._to_str(indent + " "*(1+len(node.remainder)+ 2 + len(str(self.value))))}'
        for c, node in self.children.items())

  def __str__(self):
    return self._to_str()

  def _add_child(self, char, child):
    assert child != self, char
    child_max_value = child._get_max_value_at_or_beneath()
    if self.highest_child_value_at_or_beneath < child_max_value:
      self.highest_child_value_at_or_beneath = child_max_value
      self.highest_child_char = char
    self.children[char] = child

  def get_most_recent_ancestor_or_actual(self, string, filter_fn=None):
    path = self._get_path_to(string, return_mra_on_fail=True, allow_substr=False)
    if not path:
      return None
    if filter_fn:
      for i in range(1, len(path) + 1):
        if filter_fn(path[-i][1]):
          return path[-i][1]
      return None
    return path[-1][1]

  def get_descendent_end_point_strings(self, include_node=False):
    if self.end_point:
      if include_node:
        yield self.remainder, self
      yield self.remainder
    for c, child in self.children.items():
      if include_node:
        for string, node in child.get_descendent_end_point_strings(True):
          yield f'{self.remainder}{c}{string}', node
      else:
        for string in child.get_descendent_end_point_strings():
          yield f'{self.remainder}{c}{string}'


  def _get_path_to(self, s, return_mra_on_fail=False, allow_substr=True):
    assert not (return_mra_on_fail and allow_substr)
    curr_node = self
    path = [('', curr_node)]
    sub_str = s
    while True:
      if sub_str == curr_node.remainder:
        return path  # Precise match.
      i = min(len(curr_node.remainder), len(sub_str))
      if i > 0 and sub_str[:i] != curr_node.remainder[:i]:
        if return_mra_on_fail:
          return path[:-1]  # Return up-to last node since curr_node doesn't quite match.
        break
      if i == len(sub_str):  # sub_str inside of remainder.
        if allow_substr:
          return path
        if return_mra_on_fail:
          return path[:-1]
        return None
      next_char = sub_str[i]
      try:
        curr_node = curr_node.children[next_char]
      except KeyError:
        if return_mra_on_fail:
          return path
        return None
      else:
        path.append((next_char, curr_node))
        sub_str = sub_str[i + 1:]  # May be empty string.

    return None

  def _get_max_path(self):
    curr_node = self
    chars = []
    while curr_node.value < curr_node.highest_child_value_at_or_beneath:
      chars.append(curr_node.highest_child_char)
    return ''.join(chars)

  def remove(self, string, remove_subtree=True):
    path = self._get_path_to(string, allow_substr=False)
    if not path:
      return
    # Path points exactly to string - so we can remove the node.
    remove_last_node_from_path(path, remove_subtree=remove_subtree)

  def add(self, string, value, add_value=False, store_value=None) -> 'Trie':
    '''Adds |string| to this Trie with the specified values and returns the Trie storing them.

      Important Note: The Trie this returns is guaranteed to represent string in the substructure
      unless explicitly deleted - regardless of any subsequent additions and splits. In other words,
      the Trie returned is stable.'''

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
      new_node = type(self)()  # Supports subclass.
      new_node.remainder = node.remainder[:split_point]
      c = node.remainder[split_point]
      # new_node.value = self.default_value - TODO
      new_node._add_child(c, node)
      node.remainder = node.remainder[split_point + 1:]
      # TODO: Pull this out of this function?
      if len(additional_remainder) > 0:
        new_child = type(self)()  # Supports subclass.
        new_child.end_point = True
        new_child.remainder = additional_remainder[1:]  # First char used for indexing below.
        new_child.value = additional_remainder_value
        new_node._add_child(additional_remainder[0], new_child)
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
        new_subtree.end_point = True
        new_subtree.value = value
        new_subtree.store_value = store_value
        c, parent = path[-1]
        parent.children[c] = new_subtree
        return new_subtree

      # Perfect match with curr_node - update value.
      curr_node.end_point = True
      curr_node.value = value if not add_value else curr_node.value + value
      curr_node.store_value = store_value
      last_node = curr_node
      for c, node in path[::-1]:
        last_node_max_value = last_node._get_max_value_at_or_beneath()
        if node.highest_child_value_at_or_beneath < last_node_max_value:
          node.highest_child_value_at_or_beneath = last_node_max_value
          node.highest_child_char = c
        else:
          break  # If it's not highest at this level in the tree, it won't be further up.
      return curr_node
    except RemainderSplitException as e:
      # Partially in remainder. Replace curr_node in tree with new subtree. curr_node will split
      # into 3 nodes.
      # TODO: update highest-values.
      prefix = ''.join(x[0] for x in path)
      remainder = ''.join([b] + list(string_iter))
      assert remainder
      c, parent = path[-1]
      new_node = parent.children[c] = split_node(curr_node, e.split_point, remainder, value)
      out = new_node.children[remainder[0]]
      out.end_point = True
      out.store_value = store_value
      if value > curr_node._get_max_value_at_or_beneath():
        # Need to update hierarchy.
        for c, node in path[::-1]:
          if node.highest_child_value_at_or_beneath < value:
            node.highest_child_value_at_or_beneath = value
            node.highest_child_char = c
          else:
            break  # Everything above is greater.
      return out
    except KeyError:
      # Matches current node's remainder if any - need to add as new child.
      remaining_chars = ''.join(list(string_iter))
      new_node = type(self)()  # Supports subclass.
      new_node.end_point = True
      new_node.remainder = remaining_chars
      new_node.value = value
      new_node.store_value = store_value
      old_max = curr_node._get_max_value_at_or_beneath()
      curr_node._add_child(c, new_node)
      if old_max < value:
        # Need to update hierarchy.
        for c, node in path[::-1][1:]:
          if node.highest_child_value_at_or_beneath < value:
            node.highest_child_value_at_or_beneath = value
            node.highest_child_char = c
          else:
            break  # Everything above is greater.
      return new_node
    assert False  # Unreachable - should return a node somewhere above.

  def get_node(self, string):
    path = self._get_path_to(string, allow_substr=False)
    if not path:
      return None
    return path[-1][1]

  def get_value_for_string(self, string):
    node = self.get_node(string)
    if not node:
      return 0
    return node.value

  def get_max_value_at_or_beneath_prefix(self, prefix, default=0):
    path = self._get_path_to(prefix, allow_substr=True)
    if not path:
      return default
    return path[-1][1]._get_max_value_at_or_beneath()

  def get_max(self, prefix):
    path = self._get_path_to(prefix)
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

  def has_children(self):
    return bool(self.children)


@attr.s
class FilePathTrie(Trie):
  '''A Trie which has been extended to work well with filenames (including directories) as input.

  At insertion time, any added string *must* be a valid filename that exists. Afterwards, the
  filename need no longer exist afterwards.

  Wrapping Trie for file paths helps primarily around directories and filesystem operations on the
  Trie.

  Directories are always inserted with a os.sep suffix. This way, their children are always
  guaranteed to be descendants of that directory. Otherwise, you can end up in awkward situations.

  For example given the following directory structure:
  /a/
     foo/
         b
         c
     foo_old/

  In a Trie without explicitly including os.sep as a suffix, this wil look like the following:
  /a/
     foo
        /
         b
         c
        _old

  Where the nodes containing foo & _old are marked as end_points with no explicit indication that
  they are directories.

  A few consequences are: 1) Don't have any information to indicate foo_old is a directory (no 
  children implies it might not be). 2) We cannot get 

  This matches our directory structure itself and provides a nice way to tell if any node is a
  directory.

  In a Trie with explicitly including os.sep as a suffix, this wil look like the following.
  /a/
     foo
        /
         b
         c
        _old/

  Now the nodes with '/' (after foo) and _old/ in them are marked as end_point and both are
  clearly distinct directories. Moreover, the children of both are guaranteed to be proper file
  descendents.
  '''

  def remove(self, string, remove_subtree=True):
    return super().remove(string=self._append_sep_if_needed(string), remove_subtree=remove_subtree)

  def _append_sep_if_needed(self, filename):
    if not os.path.exists(filename):
      # Damn, file already deleted - can't tell from OS if it was a dir. Need to infer from tree.
      filename_as_dir = append_sep_if_dir(filename, force=True)
      path = self._get_path_to(filename_as_dir, allow_substr=True)
      # If there is a path, then that means the filename is valid as a dir and therefore is a dir.
      if path:
        return filename_as_dir
      return filename
    # filename exists and therefore we can use the normal appending logic.
    return append_sep_if_dir(filename)

  def get_most_recent_ancestor_or_actual(self, filename, filter_fn=None):
    return super().get_most_recent_ancestor_or_actual(string=self._append_sep_if_needed(filename),
                                                      filter_fn=filter_fn)

  def add(self, filename, value, add_value=False, store_value=None) -> 'FilePathTrie':
    # filename must exist at the time of adding - otherwise we cannot infer whether it is a
    # directory to insert it correctly.
    assert os.path.exists(filename)
    return super().add(string=append_sep_if_dir(filename),
                       value=value,
                       add_value=add_value,
                       store_value=store_value)

  # TODO: This can maybe be dropped since get_value is overriden?
  def get_value_for_string(self, filename):
    return super().get_value_for_string(string=self._append_sep_if_needed(filename))

  def get_node(self, filename):
    return super().get_node(string=self._append_sep_if_needed(filename))

  def _get_paths_to_char_or_leaf(self, char, exclude_self=True):
    '''Includes char.'''

    if not exclude_self:
      path = [('', self)]
      if char in self.remainder:
        yield self.remainder[:(self.remainder.find(char) + 1)], path
        return
      elif not self.children:
        assert self.end_point
        yield self.remainder, path
        return
    else:
      path = []
    items = list(self.children.items())
    for c, child in items:
      if c == char:
        if not exclude_self:
          yield f'{self.remainder}{c}', path + [(c, child)]
        else:
          yield f'{c}', path + [(c, child)]
        continue
      for string, subpath in child._get_paths_to_char_or_leaf(char, exclude_self=False):
        subpath[0] = c, subpath[0][1]
        if not exclude_self:
          yield f'{self.remainder}{c}{string}', (path + subpath)
        else:
          yield f'{c}{string}', (path + subpath)

  def get_nodes_in_dir(self, directory):
    directory = append_sep_if_dir(directory, force=True)
    path = self._get_path_to(directory)
    if not path:
      return []
    # Directory is equal to or a higher-level directory of path.
    path_str = path_to_str(path)
    if path_str == directory:
      for substr, subpath in path[-1][1]._get_paths_to_char_or_leaf(os.sep):
        # print((substr, path_to_str(subpath)))
        if subpath:
          yield substr, (path + subpath)
      return
    # path points to a node beneath this directory.
    subpath_str = path_str[len(directory):]
    if os.sep in subpath_str:
      # Node is at least directory deeper than directory.
      yield subpath_str[:subpath_str.find(os.sep) + 1], path[-1][1]

  # TODO: Find a cleaner way to do this.
  @staticmethod
  def _deserialize(args):
    args[0] = {k: FilePathTrie._deserialize(t) for k, t in args[0].items()}
    return FilePathTrie(*args)

  @staticmethod
  def load(filename):
    with open(filename, 'rb') as f:
      return FilePathTrie._deserialize(msgpack.unpack(f, raw=False, use_list=True))


def path_to_str(path):
  # print(path)
  return ''.join(f'{x[0]}{x[1].remainder}' for x in path)


def remove_last_node_from_path(path, remove_subtree=True):
  target_char, target_node = path[-1]
  if remove_subtree:
    del path[-2][1].children[target_char]
  else:  # Just mark node as no longer being an endpoint and remove it's values.
    if target_node.end_point:
      if not target_node.children:
        # Safe to delete.
        del path[-2][1].children[target_char]
      else:
        target_node.end_point = False
        target_node.value = 0
        target_node.store_value = None
  # Update value-count hierarchy.
  for a, b in zip(path[::-1], path[::-1][1:]):
    c = a[0]
    node = b[1]

    if node.highest_child_char == c:
      # Search for new char.
      if not node.children:  # No other children.
        node.highest_child_char = ''
        node.highest_child_value_at_or_beneath = 0
      else:  # Search for next greatest child.
        child_char, child_node = max(node.children.items(),
                                     key=lambda cn: cn[1]._get_max_value_at_or_beneath())
        node.highest_child_char = child_char
        node.highest_child_value_at_or_beneath = child_node._get_max_value_at_or_beneath()
    else:
      break


def append_sep_if_dir(path, force=False):
  if os.path.isdir(path) or force:
    if path and path[-1] == os.sep:
      return path
    return f'{path}{os.sep}'
  return path
