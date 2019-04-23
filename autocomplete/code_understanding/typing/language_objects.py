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
from abc import ABC, abstractmethod
from copy import copy
from enum import Enum
from functools import wraps
from typing import Dict, Iterable

import attr

from autocomplete.code_understanding.typing.errors import (
    LoadingModuleAttributeError, SourceAttributeError)
from autocomplete.code_understanding.typing.expressions import (
    AnonymousExpression, LiteralExpression, VariableExpression)
from autocomplete.code_understanding.typing.frame import Frame, FrameType
from autocomplete.code_understanding.typing.pobjects import (NONE_POBJECT,
                                                             AugmentedObject,
                                                             FuzzyBoolean,
                                                             PObject,
                                                             UnknownObject)
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
  UNKNOWN = 4


def create_main_module(filename=None):
  return Module(
      '__main__',
      ModuleType.MAIN,
      members={},
      containing_package=None,
      filename=filename,
      is_package=False)


@attr.s(str=False, repr=False)
class Module(Namespace):
  name: str = attr.ib()
  module_type: ModuleType = attr.ib()
  _members: Dict = attr.ib()
  containing_package = attr.ib()
  filename = attr.ib()
  is_package = attr.ib()

  def __attrs_post_init__(self):
    if self.module_type == ModuleType.UNKNOWN:
      self.dynamic_creation_func = lambda name: UnknownObject(name='.'.join(
          [self.path(), name]))

  def path(self):
    return f'{self.containing_package.path()}.{self.name}' if self.containing_package else self.name

  def root(self):
    if self.containing_package:
      return self.containing_package.root()
    return self

  def __getitem__(self, name):
    try:
      return super().__getitem__(name)
    except SourceAttributeError:
      if self.module_type != ModuleType.UNKNOWN:
        warning(f'Failed to get {name} from {self.name}')
      raise


@attr.s
class LazyModule(Module):
  '''A Module which is lazily loaded with members.
  
  On the first attribute access, this module is loaded from its filename.
  '''
  load_module_exports_from_filename = attr.ib()
  _loaded = attr.ib(False)
  _loading = attr.ib(False)
  _members: Dict = attr.ib(None)

  def _lazy_load(func):

    @wraps(func)
    def _wrapper(self, *args, **kwargs):
      if not self._loaded:
        # info(f'Lazily loading from: {self.filename}')
        if self._loading:
          #
          debug(
              f'Already lazy-loading module... dependency cycle? {self.path()}. Or From import?'
          )
          raise LoadingModuleAttributeError()
          # return func(self, *args, **kwargs)
        self._loading = True
        try:
          self._members = self.load_module_exports_from_filename(
              self, self.filename)
        except ValueError:
          raise
          error(f'Unable to lazily load {self.filename}')
        self._loaded = True
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


# class CallableInterface(ABC):
#   @abstractmethod
#   def call(self, args, kwargs, args, kwargs, curr_frame): ...

#   @abstractmethod
#   def get_parameters(self): ...


@attr.s(str=False, repr=False)
class Klass(Namespace):
  name: str = attr.ib()
  context: Namespace = attr.ib()
  _members: Dict[str, PObject] = attr.ib(factory=dict)

  def __str__(self):
    return f'class {self.name}: {list(self._members.keys())}'

  def __repr__(self):
    return str(self)

  def call(self, args, kwargs, curr_frame):
    return AugmentedObject(self.new(args, kwargs, curr_frame))

  def new(self, args, kwargs, curr_frame):
    info(f'Creating instance of {self.name}')
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
        # new_func = copy(value)
        # bound_frame = new_func.get_or_create_bound_frame()
        # try:
        #   self_param = new_func.parameters.pop(0)
        #   info(f'self_param: {self_param} for {new_func}')
        #   bound_frame._locals[self_param.name] = pobject
        # except IndexError:
        #   warning(f'No self param in {new_func}')
        new_func.function_type = FunctionType.BOUND_INSTANCE_METHOD
        instance[name] = AugmentedObject(new_func)
      else:
        instance[name] = member

    if '__init__' in instance:
      # info('Calling method __init__')
      instance['__init__'].value().call(args, kwargs, curr_frame)

    return instance

  # def get_parameters(self):
  #   if '__init__' in self:
  #     return self['__init__'].get_parameters()
  #   return []


@attr.s(str=False, repr=False)
class Instance(Namespace):
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


class Function(Namespace):
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

  def call(self, args, kwargs, curr_frame):
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
        globals=self._module._members,
        cell_symbols=self._cell_symbols)
    self._process_args(args, kwargs, new_frame)
    self.graph.process(new_frame)

    return new_frame.get_returns()

  def _process_args(self, args, kwargs, curr_frame):
    param_iter = iter(self.parameters)
    arg_iter = iter(args)
    for arg, param in zip(arg_iter, param_iter):
      if param.parameter_type == ParameterType.SINGLE:
        curr_frame[param.name] = arg.evaluate(curr_frame)
      elif param.parameter_type == ParameterType.ARGS:
        curr_frame[param.name] = [arg.evaluate(curr_frame)
                                 ] + [a.evaluate(curr_frame) for a in arg_iter]
      else:  # KWARGS
        raise ValueError(
            f'Invalid number of positionals. {arg}: {args} fitting {self.parameters}'
        )

    kwargs_name = None
    for param in param_iter:
      if param.name in kwargs:
        curr_frame[VariableExpression(
            param.name)] = kwargs[param.name].evaluate(curr_frame)
      elif param.parameter_type == ParameterType.KWARGS:
        kwargs_name = param.name
      else:
        # Use default. If there's no assignment and no explicit default, this
        # will be NONE_POBJECT.
        curr_frame[VariableExpression(param.name)] = param.default

    if kwargs_name:  # Add remaining keywords to kwargs if there is one.
      in_dict = {}
      for key, value in kwargs.items():
        if key not in curr_frame:
          in_dict[key] = value
      curr_frame[kwargs_name] = AugmentedObject(in_dict)

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
    container_parameters = self._function.parameters
    remaining_parameters = container_parameters[len(self._bound_args):]
    self.parameters = filter(lambda param: param.name not in self._bound_kwargs,
                             remaining_parameters)

  # @_function.validator
  # def _function_validator(self, attribute, value):
  #   assert isinstance(value, Function)v

  # TODO: Cell vars.
  def bind(self, args, kwargs) -> 'BoundFunction':
    return BoundFunction(self, args, kwargs)

  def call(self, args, kwargs, curr_frame):
    new_frame = curr_frame.make_child(
        frame_type=FrameType.NORMAL,
        namespace=self,
        module=self._function._module)
    new_frame._locals = self._bound_locals
    return self._function.call(self._bound_args + args, {
        **kwargs,
        **self._bound_kwargs
    }, new_frame)

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

  def call(self, args, kwargs, curr_frame):
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
