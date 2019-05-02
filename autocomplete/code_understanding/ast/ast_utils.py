def _name_id_or_arg(node):
  if hasattr(node, 'name'):
    return node.name
  if hasattr(node, 'id'):
    return node.id
  if hasattr(node, 'arg'):
    return node.arg
  return None


def _complete_name(node, node_to_parent_dict, base_name='', descendents=None):
  if descendents is None:
    descendents = set()
  if node is None:
    return base_name
  parent = node_to_parent_dict[node] if node in node_to_parent_dict else None

  if parent is not None and parent in descendents:
    return base_name

  name = _name_id_or_arg(node)
  name = join_names(name, base_name)

  descendents.add(node)
  if parent is not None:
    return _complete_name(parent, node_to_parent_dict, base_name=name, descendents=descendents)
  return name
