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
from abc import ABC, abstractmethod
from copy import copy
from enum import Enum
from functools import wraps
from typing import Dict, Iterable

import attr

from autocomplete.code_understanding.typing.errors import (
    LoadingModuleAttributeError, NoDictImplementationError,
    SourceAttributeError, UnableToReadModuleFileError)
from autocomplete.code_understanding.typing.expressions import (
    AnonymousExpression, LiteralExpression, StarredExpression,
    VariableExpression)
from autocomplete.code_understanding.typing.frame import Frame, FrameType
from autocomplete.code_understanding.typing.pobjects import (
    NONE_POBJECT, AugmentedObject, FuzzyBoolean, LanguageObject, NativeObject,
    PObject, UnknownObject, pobject_from_object)
from autocomplete.code_understanding.typing.utils import instance_memoize
from autocomplete.nsn_logging import debug, error, info, warning


@attr.s
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
    return self[name]

  def set_attribute(self, name, value):
    self[name] = value


class ModuleType(Enum):
  SYSTEM = 0
  PUBLIC = 1
  LOCAL = 2
  MAIN = 3
  BUILTIN = 4
  UNKNOWN_OR_UNREADABLE = 5

  def should_be_readable(self):
    return self != ModuleType.BUILTIN and self != ModuleType.UNKNOWN_OR_UNREADABLE


def create_main_module(filename=None):
  return ModuleImpl(
      '__main__',
      ModuleType.MAIN,
      members={},
      filename=filename,
      is_package=False)


@attr.s
class Module(Namespace, LanguageObject, ABC):
  name: str = attr.ib()
  module_type: ModuleType = attr.ib()
  _members: Dict = attr.ib()
  filename = attr.ib(kw_only=True)

  def add_members(self, members):
    self._members.update(members)

  def get_members(self):
    return self._members


@attr.s
class NativeModule(Module):
  name: str = attr.ib()
  module_type: ModuleType = attr.ib()
  filename = attr.ib(kw_only=True)
  _native_module: NativeObject = attr.ib(kw_only=True)
  _members: Dict = attr.ib(init=False, default=None)  # TODO: Remove.

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

  @instance_memoize
  def root(self):
    return self


@attr.s
class ModuleImpl(Module):
  # This will include containing packages, if any. i.e. a.b.c for module c.
  name: str = attr.ib()
  module_type: ModuleType = attr.ib()
  filename = attr.ib(kw_only=True)
  _is_package = attr.ib(kw_only=True)
  _members: Dict = attr.ib(kw_only=True)

  def __attrs_post_init__(self):
    self._members['__package__'] = self._members[
        '__name__'] = pobject_from_object(self.name)
    self._members['__path__'] = self._members['__file__'] = pobject_from_object(
        self.filename)
    self._members['__loader__'] = UnknownObject('__loader__')

  def __getitem__(self, name):
    try:
      return super().__getitem__(name)
    except SourceAttributeError:
      if self.module_type.should_be_readable():
        warning(f'Failed to get {name} from {self.name}')
      return UnknownObject(f'{self.name}.{name}')


@attr.s
class SimplePackageModule(ModuleImpl):
  ...


@attr.s
class LazyModule(ModuleImpl):
  '''A Module which is lazily loaded with members.
  
  On the first attribute access, this module is loaded from its filename.
  '''
  load_module_exports_from_filename = attr.ib(kw_only=True)
  _loaded = attr.ib(init=False, default=False)
  _loading = attr.ib(init=False, default=False)
  _loading_failed = attr.ib(init=False, default=False)
  _members: Dict = attr.ib(init=False, factory=dict)

  def _lazy_load(func):

    @wraps(func)
    def _wrapper(self, *args, **kwargs):
      if not self._loaded and not self._loading_failed:
        if self._loading:
          # debug(f'Lazily loading from: {self.filename}')
          # So, curiously, this is more allowed than I would think. ctypes does this with _endian
          # where ctypes imports some stuff from _endian and the latter imports everything from
          # ctypes - however, the ordering seems carefully done such that the _endian import in
          # ctypes is well after most of it's members are defined - so, the module is mostly defined.
          warning(
              f'Already lazy-loading module... dependency cycle? {self.name}. Or From import?'
          )
          return func(self, *args, **kwargs)
          # raise LoadingModuleAttributeError()
        self._loading = True
        try:
          self._members = self.load_module_exports_from_filename(
              self, self.filename)
        except UnableToReadModuleFileError:
          # raise
          error(f'Unable to lazily load {self.filename}')
          self._loading_failed = True
        else:
          self._loaded = True
        finally:
          self._loading = False
      return func(self, *args, **kwargs)

    return _wrapper

  @_lazy_load
  def __contains__(self, name):
    return super().__contains__(name)

  @_lazy_load
  def __getitem__(self, name):
    return super().__getitem__(name)

  @_lazy_load
  def __setitem__(self, name, value):
    super().__setitem__(name, value)

  @_lazy_load
  def items(self):
    return super().items()


@attr.s(str=False, repr=False)
class Klass(Namespace, LanguageObject):
  name: str = attr.ib()
  context: Namespace = attr.ib()
  _members: Dict[str, PObject] = attr.ib(factory=dict)

  def __str__(self):
    return f'class {self.name}: {list(self._members.keys())}'

  def __repr__(self):
    return str(self)

  def call(self, curr_frame, args, kwargs):
    return AugmentedObject(self.new(curr_frame, args, kwargs))

  def new(self, curr_frame, args, kwargs):
    debug(f'Creating instance of {self.name}')
    # TODO: Handle params.
    # TODO: __init__
    instance = Instance(self)
    for name, member in self.items():
      if member.value_is_a(
          Function
      ) == FuzzyBoolean.TRUE:  # and value.type == FunctionType.UNBOUND_INSTANCE_METHOD:
        value = member.value(
        )  # TODO: This can raise an exception for FuzzyObjects
        new_func = value.bind([AnonymousExpression(self)], {})
        new_func.function_type = FunctionType.BOUND_INSTANCE_METHOD
        instance[name] = AugmentedObject(new_func)
      else:
        instance[name] = member

    if '__init__' in instance:
      # info('Calling method __init__')
      instance['__init__'].value().call(curr_frame, args, kwargs)

    return instance

  # def get_parameters(self):
  #   if '__init__' in self:
  #     return self['__init__'].get_parameters()
  #   return []


@attr.s(str=False, repr=False)
class Instance(Namespace, LanguageObject):
  klass = attr.ib()
  _members: Dict = attr.ib(factory=dict)

  # TODO: Class member fallback for classmethods?

  def __str__(self):
    return f'Inst {self.klass.name}: {list(self._members.keys())}'

  def __repr__(self):
    return str(self)


class FunctionType(Enum):
  FREE = 0
  CLASS_METHOD = 1
  STATIC_METHOD = 2  # Essentially, free.
  UNBOUND_INSTANCE_METHOD = 3
  BOUND_INSTANCE_METHOD = 4


class Function(Namespace, LanguageObject):
  ...


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
    debug(f'Calling {self.name}')
    if curr_frame.contains_namespace_on_stack(self):
      debug(
          f'Call being made into {self.name} when it\'s already on the call stack. Returning an UnknownObject instead.'
      )
      # TODO: Search for breakout condition somehow?
      return UnknownObject(self.name)
    new_frame = curr_frame.make_child(
        frame_type=FrameType.FUNCTION,
        namespace=self,
        module=self._module,
        cell_symbols=self._cell_symbols)
    new_frame._locals.update(bound_locals)

    self._process_args(curr_frame, args, kwargs, new_frame)
    self.graph.process(new_frame)

    return new_frame.get_returns()

  def call(self, curr_frame, args, kwargs):
    return self.call_inner(curr_frame, args, kwargs, bound_locals={})

  def _process_args(self, curr_frame, args, kwargs, new_frame):
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
        if isinstance(arg, StarredExpression):  # Passed *iterable or **dict.
          results = arg.base_expression.evaluate(curr_frame)
          if arg.operator == '*':
            iterator = iter(results.iterator())
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
              result_dict = results.to_dict()
              kwarg_param_name = None
              kwarg_remaining = {}
              param_set = set()
              for param in itertools.chain([param], param_iter):
                if param.parameter_type == ParameterType.SINGLE:
                  param_set.add(param.name)
                elif param.parameter_type == ParameterType.KWARGS:
                  kwarg_param_name = param.name

              for key, value in result_dict.items():
                value = pobject_from_object(value)
                if key in param_set:
                  new_frame[key] = value
                else:
                  kwarg_remaining[key] = value
              if kwarg_param_name:
                new_frame[kwarg_param_name] = pobject_from_object(
                    kwarg_remaining)
              elif kwarg_remaining:  # non-empty.
                error(
                    f'No **kwargs but had unassigned kwargs: {kwarg_remaining}')
            except NoDictImplementationError:
              pass  # Non-NativeObject. Too fancy for us.
            break
        # Normal case.
        new_frame[param.name] = arg.evaluate(curr_frame)
      elif param.parameter_type == ParameterType.ARGS:
        # Collect all remaining positional arguments into *args param
        args = []
        for a in itertools.chain([arg], arg_iter):
          if isinstance(a, StarredExpression):  # Passing in *iterable.
            args += list(a.base_expression.evaluate(curr_frame).iterator())
          else:  # Normal positional.
            args.append(a.evaluate(curr_frame))

        new_frame[param.name] = pobject_from_object(args)
        break
      else:  # KWARGS
        error(
            f'Invalid number of positionals. {arg}: {args} fitting {self.parameters}'
        )

    # Process keyword-arguments.
    kwargs_name = None
    for param in param_iter:
      if param.name in kwargs:
        new_frame[param.name] = kwargs[param.name].evaluate(curr_frame)
      elif param.parameter_type == ParameterType.KWARGS:
        kwargs_name = param.name
      else:
        # Use default. If there's no assignment and no explicit default, this
        # will be NONE_POBJECT.
        new_frame[param.name] = param.default

    if kwargs_name:  # Add remaining keywords to kwargs if there is one.
      in_dict = {}
      for key, value in kwargs.items():
        if key not in new_frame:
          in_dict[key] = value
      new_frame[kwargs_name] = pobject_from_object(in_dict)  # NativeObject.

  def __str__(self):
    return f'def {self.name}({tuple(self.parameters)})'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
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
    container_parameters = list(self._function.parameters)
    remaining_parameters = container_parameters[len(self._bound_args):]
    self.parameters = filter(lambda param: param.name not in self._bound_kwargs,
                             remaining_parameters)

  # @_function.validator
  # def _function_validator(self, attribute, value):
  #   assert isinstance(value, Function)v

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
    # if reuse_curr_frame:
    #   new_frame = curr_frame
    # else:
    #   new_frame = curr_frame.make_child(
    #       frame_type=FrameType.FUNCTION,
    #       namespace=self,
    #       module=self._function._module)
    # new_frame._locals.update(self._bound_locals)
    return self._function.call_inner(curr_frame, self._bound_args + args, {
        **kwargs,
        **self._bound_kwargs
    }, self._bound_locals)

  def __str__(self):
    return f'bound[{self._bound_args}][{self._bound_kwargs}]:{self._function}'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
class StubFunction(Function):
  name: str = attr.ib()
  parameters = attr.ib()
  returns = attr.ib()
  type = attr.ib(FunctionType.FREE)
  _members: Dict = attr.ib(factory=dict)

  def call_inner(self, curr_frame, args, kwargs, bound_locals):
    # TODO: Handle parameters?
    return self.returns

  def call(self, curr_frame, args, kwargs, reuse_curr_frame=False):
    # TODO: Handle parameters?
    return self.returns

  def get_parameters(self, curr_frame):
    return self.parameters

  def __str__(self):
    return f'Func({tuple(self.parameters)})'

  def __repr__(self):
    return str(self)


@attr.s(str=False, repr=False)
class Parameter:
  name: str = attr.ib()
  parameter_type: 'ParameterType' = attr.ib()
  default: 'Expression' = attr.ib(None)  # TODO: Rename default_expression

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


class ParameterType(Enum):
  SINGLE = 0
  ARGS = 1
  KWARGS = 2
