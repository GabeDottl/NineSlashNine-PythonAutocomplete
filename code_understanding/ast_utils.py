
def _name_or_id(node):
  if hasattr(node, 'name'):
    return node.name
  if hasattr(node, 'id'):
    return node.id
  return None
