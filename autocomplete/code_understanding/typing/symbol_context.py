import itertools

import attr


class SymbolContext:
  def merge(self, other):
    return MultipleSymbolContext([self, other])


@attr.s
class RawSymbolContext(SymbolContext):
  parse_node = attr.ib()


# parse_node = attr.ib()

# @attr.s
# class SubclassSymbolContext(SymbolContext):
#   parse_node = attr.ib()


@attr.s
class CallSymbolContext(SymbolContext):
  args = attr.ib()
  kwargs = attr.ib()
  parse_node = attr.ib()


@attr.s
class SubscriptSymbolContext(SymbolContext):
  index = attr.ib()
  parse_node = attr.ib()


@attr.s
class AttributeSymbolContext(SymbolContext):
  attribute = attr.ib()
  parse_node = attr.ib()


@attr.s
class MultipleSymbolContext(SymbolContext):
  contexts = attr.ib(default=list)

  def __attrs_post_init__(self):
    tmp = []
    for c in self.contexts:
      # Flatten
      if isinstance(c, MultipleSymbolContext):
        tmp += c.contexts
      else:
        if not isinstance(c, RawSymbolContext):
          tmp.append(c)

    if not tmp:
      tmp.append(RawSymbolContext)
    self.contexts = tmp


def merge_symbol_context_dicts(*args):
  # assert len(args) > 1
  if not args:
    return {}

  if len(args) == 1:
    return args[0]

  out = {**args[0]}
  for symbol, context in itertools.chain(*[a.items() for a in args[1:]]):
    if symbol in out:
      out[symbol] = out[symbol].merge(context)
    else:
      out[symbol] = context
  return out

  # def add(self, context):
  #   self.contexts.append(context)

  # def merge(self, other)