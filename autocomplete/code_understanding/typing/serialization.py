from typing import Iterable

from .utils import attrs_names_from_class, to_dict_iter

NONE_TYPE = type(None)


def deserialize(type_str, serialized_obj, hook_fn=None):
  from .pobjects import UnknownObject, NativeObject, AugmentedObject, FuzzyBoolean
  from .language_objects import (Parameter, ParameterType, StubFunction, FunctionType, ModuleImpl,
                                 Klass, LazyInstance)
  if serialized_obj is None:
    return None
  if type_str in __builtins__:
    return serialized_obj

  if hook_fn:
    success, obj = hook_fn(type_str, serialized_obj)
    if success:
      return obj

  type_ = locals()[type_str]
  if hasattr(type_, 'deserialize'):
    return type_.deserialize(serialized_obj)

  if isinstance(serialized_obj, dict):
    d = {}
    for key, value in serialized_obj.items():
      d[key] = deserialize(*value)
    return type_(**d)

  return type_(serialized_obj)


def serialize(obj, hook_fn=None, **kwargs):
  if hook_fn:
    success, serialized = hook_fn(obj)
    if success:
      return serialized

  if isinstance(obj, (str, int, float, bool, NONE_TYPE)):
    return type_name(obj), obj

  if hasattr(obj, 'serialize'):
    return obj.serialize(hook_fn=hook_fn, **kwargs)

  # Check if attrs class.
  if hasattr(obj, '__attrs_attrs__'):
    out = {}
    attr_names = set(attrs_names_from_class(obj))
    for name, value in filter(lambda k, v: k in attr_names, to_dict_iter(obj)):
      out[name] = serialize(value, hook_fn=hook_fn, **kwargs)
    return type_name(obj), out

  if isinstance(obj, dict):
    return type_name(obj), {k: serialize(v, hook_fn=hook_fn, **kwargs) for k, v in obj.items()}

  if isinstance(obj, Iterable):
    return type_name(obj), list(serialize(x, hook_fn=hook_fn, **kwargs) for x in obj)

  raise NotImplementedError()


def type_name(obj):
  if hasattr(obj, '__class__'):
    return obj.__class__.__qualname__
    # return f'{obj.__class__.__module__}.{obj.__class__.__qualname__}'
  return str(type(obj))
