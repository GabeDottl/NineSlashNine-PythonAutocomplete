'''This module contains the core language abstractions used in Python that we care about modeling.

In general, these are "heavy" abstractions meaning they carry a lot of data potentially in them
which makes them less practical for exporting. We essentially want stubs for exports.

The fact that this is python wrapping python adds some complexity to things. Namely, things like
subscripting, getting/setting attributes, or calling with objects could refer to the object
being represented (e.g. the 'foo' Function in the source we're analyzing) or refer to the pythonic
operation on the abstraction itself (e.g. Function, Klass, FuzzyObject).

In general, we work around this by using non-dunder methods that match the dunder equivalents.
So __getitem__, __getattribute__, __call__, etc. translate into get_item, get_attribute, call.
'''
import itertools
import os
from abc import ABC, abstractmethod
from copy import copy
from enum import Enum
from functools import wraps
from typing import Dict, Iterable

import attr
from . import collector, serialization, errors
from .errors import (LoadingModuleAttributeError, NoDictImplementationError, SourceAttributeError,
                     UnableToReadModuleFileError)
from .expressions import (AnonymousExpression, LiteralExpression, StarredExpression, VariableExpression)
from .frame import Frame, FrameType
from .pobjects import (NONE_POBJECT, AugmentedObject, FuzzyBoolean, LanguageObject, LazyObject, NativeObject,
                       PObject, PObjectType, UnknownObject, pobject_from_object)
from .serialization import type_name
from .utils import (attrs_names_from_class, instance_memoize)
from ...nsn_logging import debug, error, info, warning


@attr.s(slots=True)
class Namespace:
  '''A Namespace is a container for named objects.

  Not to be confused with namespaces in the context of other languages, although same idea.

  This is rather similar to the model used in CPython itself in which namespaces are implemented
  with dicts.

  https://docs.python.org/3/reference/executionmodel.html#naming-and-binding
  https://tech.blog.aknin.name/2010/06/05/pythons-innards-naming/
  '''
  # name: str = attr.ib()
  # We wrap a dict explicitly rather than subclassing to avoid certain odd behavior - e.g. __bool__
  # being overridden s.t. if there are no members, it will return false.
  _members: Dict[str, PObject] = attr.ib(factory=dict)

  def __contains__(self, name):
    return name in self._members

  # TODO: This is broken - Namespaces use the same thing for attributes and subscripts.
  def __getitem__(self, name):
    try:
      return self._members[name]  # TODO: Re-raise as SourceAttributeError
    except KeyError as e:
      raise SourceAttributeError(e)

  def __setitem__(self, name, value):
    assert isinstance(value, PObject)
    self._members[name] = value

  def items(self):
    return self._members.items()

  # TODO: delete these?
  def has_attribute(self, name):
    return name in self

  def get_attribute(self, name):
    out = self[name]
    assert isinstance(out, PObject)
    return out

  def set_attribute(self, name, value):
    assert isinstance(value, PObject)
    self[name] = value


class ModuleType(Enum):
  SYSTEM = 0
  PUBLIC = 1
  LOCAL = 2
  MAIN = 3
  BUILTIN = 4
  COMPILED = 5  # .so files.
  UNKNOWN_OR_UNREADABLE = 6

  def should_be_readable(self):
    return self != ModuleType.BUILTIN and self != ModuleType.UNKNOWN_OR_UNREADABLE

  def serialize(self, **kwargs):
    return ModuleType.__qualname__, self.value

  def is_native(self):
    return self == ModuleType.BUILTIN or self == ModuleType.COMPILED


def create_main_module(module_loader, filename=None):
  return ModuleImpl('__main__',
                    ModuleType.MAIN,
                    members={},
                    filename=filename,
                    is_package=False,
                    module_loader=module_loader)


@attr.s(slots=True)
class Module(Namespace, LanguageObject, ABC):
  name: str = attr.ib()
  module_type: ModuleType = attr.ib()
  _members: Dict = attr.ib()

  def add_members(self, members):
    self._members.update(members)

  def get_members(self):
    return self._members


@attr.s(slots=True)
class NativeModule(Module):
  name: str = attr.ib()
  module_type: ModuleType = attr.ib()
  _members: Dict = attr.ib(init=False, default=None)  # TODO: Remove.
  graph = attr.ib(None, init=False)
  _native_module: NativeObject = attr.ib(kw_only=True)
  filename = attr.ib(kw_only=True)

  def __contains__(self, name):
    return self._native_module.has_attribute(name)

  # TODO: This is broken - Namespaces use the same thing for attributes and subscripts.
  def __getitem__(self, name):
    return self._native_module.get_attribute(name)

  def __setitem__(self, index, value):
    assert False, 'Should not __setitem__ on NativeModules...'
    self._native_module.set_attribute(index, value)

  def items(self):
    return self.get_members().items()

  # TODO: delete these?
  def has_attribute(self, name):
    return self._native_module.has_attribute(name)

  def get_attribute(self, name):
    return self._native_module.get_attribute(name)

  def set_attribute(self, name, value):
    # assert False, 'Should not set_attribute on NativeModules...'
    self._native_module.set_attribute(name, value)

  def add_members(self, members):
    assert False, 'Should not add_members on NativeModules...'
    # self._members.update(members)

  def get_members(self):
    return self._native_module.to_dict()

  def root(self):
    return self

  def serialize(self, **kwargs):
    return NativeModule.__qualname__, self.name


@attr.s(slots=True)
class ModuleImpl(Module):
  # This will include containing packages, if any. i.e. a.b.c for module c.
  name: str = attr.ib()
  module_type: ModuleType = attr.ib()
  filename = attr.ib(kw_only=True)
  _is_package = attr.ib(kw_only=True)
  _members: Dict = attr.ib(kw_only=True)
  graph = attr.ib(None, kw_only=True)
  module_loader = attr.ib(kw_only=True)

  @staticmethod
  def get_module_builtin_symbols():
    return ['__package__', '__name__', '__path__', '__file__', '__loader__']

  def __attrs_post_init__(self):
    self._members['__package__'] = self._members['__name__'] = pobject_from_object(self.name)
    self._members['__path__'] = self._members['__file__'] = pobject_from_object(self.filename)
    self._members['__loader__'] = UnknownObject('__loader__')

  def __getitem__(self, name):
    try:
      return super().__getitem__(name)
    except SourceAttributeError:
      if not self.module_type.should_be_readable():
        return UnknownObject(f'{self.name}.{name}')
      if self._is_package:
        try:
          return AugmentedObject(
              self.module_loader.get_module(f'.{name}',
                                            os.path.dirname(self.filename),
                                            unknown_fallback=False))
        except errors.InvalidModuleError as e:
          pass
      if self.module_type.should_be_readable():
        warning(f'Failed to get {name} from {self.name}')
      return UnknownObject(f'{self.name}.{name}')

  def serialize(self, **kwargs):
    # Note, this is being done s.t. it works with subclasses - namely LazyModule.
    d = {}

    def serialization_hook(obj):
      if isinstance(obj, Module):
        return True, ('import_module', (obj.name, obj.filename))
      if isinstance(obj, Klass) and obj.module_name != self.name:
        return True, ('from_import', obj.name)
      return False, None

    for name in attrs_names_from_class(ModuleImpl):
      value = getattr(self, name)
      # Don't try persisting the graph if there is one.
      if name == 'graph':
        continue

      value = serialization.serialize(value, hook_fn=serialization_hook)
      d[_strip_underscore_prefix(name)] = value
    return ModuleImpl.__qualname__, d


def _strip_underscore_prefix(name):
  for i in range(len(name)):
    if name[i] != '_':
      return name[i:]
  return ''


@attr.s(slots=True)
class SimplePackageModule(ModuleImpl):
  ...


def _lazy_load(func):
  @wraps(func)
  def _wrapper(self, *args, **kwargs):
    self.load()
    if self._loading:
      # debug(f'Lazily loading from: {self.filename}')
      # So, curiously, this is more allowed than I would think. ctypes does this with _endian
      # where ctypes imports some stuff from _endian and the latter imports everything from
      # ctypes - however, the ordering seems carefully done such that the _endian import in
      # ctypes is well after most of it's members are defined - so, the module is mostly defined.
      warning(f'Already lazy-loading module... dependency cycle? {self.name}. Or From import?')
    return func(self, *args, **kwargs)

  return _wrapper


def _passthrough_to_super_if_loaded(func):
  @wraps(func)
  def wrapper(self, *args, **kwargs):
    if self._loaded:
      return getattr(super(), func.__name__)(*args, **kwargs)
    return func(self, *args, **kwargs)

  return wrapper


@attr.s
class LazyModule(ModuleImpl):
  '''A Module which is lazily loaded with members.

  On the first attribute access, this module is loaded from its filename.
  '''

  lazy = attr.ib(init=False, default=True)
  _loaded = attr.ib(init=False, default=False)
  _loading = attr.ib(init=False, default=False)
  _loading_failed = attr.ib(init=False, default=False)
  _members: Dict = attr.ib(init=False, factory=dict)
  graph = attr.ib(None, init=False)

  filename = attr.ib(kw_only=True)
  _is_package = attr.ib(kw_only=True)
  keep_graph = attr.ib(False, kw_only=True)
  load_module_exports_from_filename = attr.ib(kw_only=True)

  def has_loaded_or_loading(self):
    return self._loaded or self._loading_failed or self._loading

  def load(self):
    if self.has_loaded_or_loading():
      return

    self._loading = True
    try:
      if self.keep_graph:
        _, self.graph = self.load_module_exports_from_filename(self, self.filename, return_graph=True)
      else:
        _ = self.load_module_exports_from_filename(self, self.filename)
    except UnableToReadModuleFileError:
      error(f'Unable to lazily load {self.filename}')
    else:
      self._loaded = True
    finally:
      self._loading_failed = not self._loaded
      self._loading = False

  def _get_loaded(self):
    self.load()
    return self

  @_lazy_load
  def __contains__(self, name):
    return super().__contains__(name)

  def _get_item_loaded(self, name):
    self.load()
    return super().__getitem__(name)

  # @_passthrough_to_super_if_loaded
  def __getitem__(self, name):
    if self.lazy:
      return LazyObject(f'{self.name}.{name}', lambda: self._get_item_loaded(name))
    return self._get_item_loaded(name)
    # return super().__getitem__(name)

  def __setitem__(self, name, value):
    super().__setitem__(name, value)

  @_lazy_load
  def get_members(self):
    return super().get_members()

  @_lazy_load
  def items(self):
    return super().items()

  def serialize(self, **kwargs):
    assert not self._loading
    if not self._loaded or self._loading_failed:
      self.load()
    # Loaded or loading failed.
    return super().serialize(**kwargs)


@attr.s(str=False, repr=False, slots=True)
class Klass(Namespace, LanguageObject):
  name: str = attr.ib()
  module_name: 'str' = attr.ib()
  _members: Dict[str, PObject] = attr.ib(factory=dict)

  def call(self, curr_frame, args, kwargs):
    return AugmentedObject(self.new(curr_frame, args, kwargs))

  def new(self, curr_frame, args, kwargs):
    debug(f'Creating instance of {self.name}')
    # TODO: Handle params.
    # TODO: __init__
    instance = Instance(self)
    for name, member in self.items():
      # This AugmentedObject bit is a small, but rather helpful cheat. Any functions
      # actually defined within this class should be AugmentedObjects. This avoid's risking loading
      # a LazyObject prematurely.
      if isinstance(member, AugmentedObject) and member.value_is_a(
          Function) == FuzzyBoolean.TRUE:  # and value.type == FunctionType.UNBOUND_INSTANCE_METHOD:
        value = member.value()  # TODO: This can raise an exception for FuzzyObjects
        new_func = value.bind([AugmentedObject(self)], {})
        new_func.function_type = FunctionType.BOUND_INSTANCE_METHOD
        instance[name] = AugmentedObject(new_func)
      else:
        instance[name] = member

    if '__init__' in instance:
      instance['__init__'].value().call(curr_frame, args, kwargs)

    return instance

  def __str__(self):
    return f'class {self.name}: {list(self._members.keys())}'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False, slots=True)
class Instance(Namespace, LanguageObject):
  _klass = attr.ib()
  _members: Dict = attr.ib(factory=dict)

  # TODO: Class member fallback for classmethods?

  def serialize(self, **kwargs):
    return 'LazyInstance', self._klass.name

  def __str__(self):
    return f'Inst {self._klass.name}: {list(self._members.keys())}'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False, slots=True)
class LazyInstance(Namespace, LanguageObject):
  '''An unintialized or partially initialized instance.

  The main value of this is to allow us to have a notion that we have an instance of some type/class
  X, but we don't need to actually define what X is or know what member this derives from X until
  they're needed.
  '''
  klass_name = attr.ib()
  _members: Dict = attr.ib(factory=dict)

  def serialize(self, **kwargs):
    return 'LazyInstance', self._klass_name


class FunctionType(Enum):
  FREE = 0
  CLASS_METHOD = 1
  STATIC_METHOD = 2  # Essentially, free.
  UNBOUND_INSTANCE_METHOD = 3
  BOUND_INSTANCE_METHOD = 4

  def serialize(self, **kwargs):
    return FunctionType.__qualname__, self.value


class Function(Namespace, LanguageObject):
  ...

  def to_stub(self):
    return StubFunction(self.name, self.parameters, None)


@attr.s(str=False, repr=False)
class FunctionImpl(Function):
  '''FunctionImpl is a Function with it's inner CFG included.

  The trickiest thing in this are closure - which are nicely demonstrated within Python here:
  https://gist.github.com/DmitrySoshnikov/700292

  Lexical scoping with Python can be somewhat difficult to get working because of closure.
  Here's another article:
  https://medium.com/@dannymcwaves/a-python-tutorial-to-understanding-scopes-and-closure-c6a3d3ba0937


  '''
  name: str = attr.ib()
  namespace: Namespace = attr.ib()
  parameters: Iterable['Parameter'] = attr.ib()
  graph: 'CfgNode' = attr.ib()
  _module = attr.ib(validator=attr.validators.instance_of(Module))
  _cell_symbols: Iterable[str] = attr.ib()
  _type = attr.ib(FunctionType.FREE)
  _members: Dict = attr.ib(factory=dict)

  # TODO: Cell vars.
  def bind(self, args, kwargs) -> 'BoundFunction':
    return BoundFunction(self, args, kwargs)

  def call_inner(self, curr_frame, args, kwargs, bound_locals):
    if curr_frame.contains_namespace_on_stack(self):
      debug(
          f'Call being made into {self.name} when it\'s already on the call stack. Returning an UnknownObject instead.'
      )
      # TODO: Search for breakout condition somehow?
      return UnknownObject(self.name)
    new_frame = curr_frame.make_child(frame_type=FrameType.FUNCTION,
                                      namespace=self,
                                      module=self._module,
                                      cell_symbols=self._cell_symbols)
    new_frame._locals.update(bound_locals)

    self._process_args(args, kwargs, new_frame)
    with collector.FileContext(self._module.filename):
      self.graph.process(new_frame)

    return new_frame.get_returns()

  def call(self, curr_frame, args, kwargs):
    return self.call_inner(curr_frame, args, kwargs, bound_locals={})

  def _process_args(self, args, kwargs, new_frame):
    # As a sort of safety measure, we explicitly provide some value for every single param - this
    # avoids any issues with missing symbols when processing the function if it was called with
    # invalid arguments.

    # TODO: Perhaps don't call into it in that case instead as Python should do as well? This
    # could/will probably leak through bugs.
    for param in self.parameters:
      new_frame[param.name] = UnknownObject(param.name)

    # Process positional arguments.
    param_iter = iter(self.parameters)
    arg_iter = iter(args)
    for arg, param in zip(arg_iter, param_iter):
      if param.parameter_type == ParameterType.SINGLE:
        if arg.pobject_type != PObjectType.NORMAL:  # Passed *iterable or **dict.
          if arg.pobject_type == PObjectType.STARRED:
            iterator = iter(arg.iterator())
            try:
              new_frame[param.name] = next(iterator)
            except StopIteration:
              # Prepend param back to param_iter to ensure we set it in kwargs section.
              param_iter = itertools.chain([param], param_iter)
            for evaluated_arg, param in zip(iterator, param_iter):
              new_frame[param.name] = evaluated_arg
            break  # No more positionals allowed after *iterable.
          else:  # **dict
            try:
              input_kwargs_dict = arg.to_dict()
              kwarg_param_name = None
              kwarg_remaining = {}
              param_set = set()
              for param in itertools.chain([param], param_iter):
                if param.parameter_type == ParameterType.SINGLE:
                  param_set.add(param.name)
                elif param.parameter_type == ParameterType.KWARGS:
                  kwarg_param_name = param.name

              for key, value in input_kwargs_dict.items():
                value = pobject_from_object(value)
                if key in param_set:
                  new_frame[key] = value
                else:
                  kwarg_remaining[key] = value
              if kwarg_param_name:
                new_frame[kwarg_param_name] = pobject_from_object(kwarg_remaining)
              elif kwarg_remaining:  # non-empty.
                error(f'No **kwargs but had unassigned kwargs: {kwarg_remaining}')
            except NoDictImplementationError:
              pass  # Non-NativeObject. Too fancy for us.
            break
        # Normal case.
        new_frame[param.name] = arg
      elif param.parameter_type == ParameterType.ARGS:
        # Collect all remaining positional arguments into *args param
        args = []
        for a in itertools.chain([arg], arg_iter):
          if a.pobject_type == PObjectType.STARRED:  # Passing in *iterable.
            args += list(a.iterator())
          else:  # Normal positional.
            args.append(a)

        new_frame[param.name] = pobject_from_object(args)
        break
      else:  # KWARGS
        error(f'Invalid number of positionals. {arg}: {args} fitting {self.parameters}')

    # Process keyword-arguments.
    kwargs_name = None
    for param in param_iter:
      if param.name in kwargs:
        new_frame[param.name] = kwargs[param.name]
      elif param.parameter_type == ParameterType.KWARGS:
        kwargs_name = param.name
      else:
        # Use default. If there's no assignment and no explicit default, this
        # will be NONE_POBJECT.
        new_frame[param.name] = param.default_value

    if kwargs_name:  # Add remaining keywords to kwargs if there is one.
      in_dict = {}
      for key, value in kwargs.items():
        if key not in new_frame:
          in_dict[key] = value
      new_frame[kwargs_name] = pobject_from_object(in_dict)  # NativeObject.

  def serialize(self, **kwargs):
    return serialization.serialize(self.to_stub(), **kwargs)

  def __str__(self):
    return f'def {self.name}({tuple(self.parameters)})'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False, slots=True)
class BoundFunction(Function):
  _function = attr.ib(validator=attr.validators.instance_of(Function))
  # We use a notion of a 'bound frame' to encapsulate values which are
  # bound to this function - e.g. cls & self, nonlocals in a nested func.
  # bound_frame = None
  _bound_args = attr.ib(factory=list)
  _bound_kwargs = attr.ib(factory=dict)
  _bound_locals = attr.ib(factory=dict)  # For nested functions.
  _members: Dict = attr.ib(factory=dict)

  def __attrs_post_init__(self):
    self.name = self._function.name
    # container_parameters = list(self._function.parameters)
    # remaining_parameters = container_parameters[len(self._bound_args):]
    self.parameters = filter(lambda param: param.name not in self._bound_kwargs, self._function.parameters)

  # TODO: Cell vars.
  def bind(self, args, kwargs) -> 'BoundFunction':
    return BoundFunction(self, args, kwargs)

  def call_inner(self, curr_frame, args, kwargs, bound_locals):
    return self._function.call_inner(curr_frame, self._bound_args + args, {
        **kwargs,
        **self._bound_kwargs
    }, {
        **bound_locals,
        **self._bound_locals
    })

  def call(self, curr_frame, args, kwargs, reuse_curr_frame=False):
    return self._function.call_inner(curr_frame, self._bound_args + args, {
        **kwargs,
        **self._bound_kwargs
    }, self._bound_locals)

  def serialize(self, **kwargs):
    return serialization.serialize(self.to_stub(), **kwargs)

  def __str__(self):
    return f'bound[{self._bound_args}][{self._bound_kwargs}]:{self._function}'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False, slots=True, frozen=True)
class StubFunction(Function):
  name: str = attr.ib()
  parameters = attr.ib()
  returns = attr.ib()
  # type = attr.ib(FunctionType.FREE)
  _members: Dict = attr.ib(factory=dict)

  def call_inner(self, curr_frame, args, kwargs, bound_locals):
    # TODO: Handle parameters?
    return self.returns

  def call(self, curr_frame, args, kwargs, reuse_curr_frame=False):
    return self.returns

  def get_parameters(self, curr_frame):
    return self.parameters

  def to_stub(self):
    return self

  # def serialize(self, **kwargs):
  #   return serialization.serialize(self, **kwargs)

  def __str__(self):
    return f'Func({tuple(self.parameters)})'

  def __repr__(self):
    return str(self)


class ParameterType(Enum):
  SINGLE = 0
  ARGS = 1
  KWARGS = 2

  def serialize(self, **kwargs):
    return ParameterType.__qualname__, self.value


@attr.s(str=False, repr=False, slots=True, frozen=True)
class Parameter:
  name: str = attr.ib()
  parameter_type: 'ParameterType' = attr.ib()
  default_expression: 'Expression' = attr.ib(None, kw_only=True)  # TODO: Rename default_expression
  default_value: 'PObject' = attr.ib(None, kw_only=True)
  type_hint_expression: 'PObject' = attr.ib(None, kw_only=True)
  

  def __attrs_post_init__(self):
    # These cannot both be specified. Once a parameter has been processed (i.e. Function has been
    # created and added to frame), the default_value should be set,
    assert self.default_value is None or self.default_expression is None

  def __str__(self):
    if self.parameter_type == ParameterType.SINGLE:
      prefix = ''
    elif self.parameter_type == ParameterType.ARGS:
      prefix = '*'
    else:
      prefix = '**'
    return f'{prefix}{self.name}'

  def __repr__(self):
    return str(self)
