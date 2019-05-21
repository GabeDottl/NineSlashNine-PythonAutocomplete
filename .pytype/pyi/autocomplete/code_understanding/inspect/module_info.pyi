# (generated with --quick)

import __builtin__
import collections
from typing import Any, Callable, Iterable, List, Sized, Tuple, TypeVar, Union

importlib: module
inspect: module
os: module
pd: Any
pkgutil: module
sys: module

_Tnamedtuple-MemberInfo-module-member_name-member-type-module_path = TypeVar('_Tnamedtuple-MemberInfo-module-member_name-member-type-module_path', bound=`namedtuple-MemberInfo-module-member_name-member-type-module_path`)

class `namedtuple-MemberInfo-module-member_name-member-type-module_path`(tuple):
    __slots__ = ["member", "member_name", "module", "module_path", "type"]
    __dict__: collections.OrderedDict[str, Any]
    _fields: Tuple[str, str, str, str, str]
    member: Any
    member_name: Any
    module: Any
    module_path: Any
    type: Any
    def __getnewargs__(self) -> Tuple[Any, Any, Any, Any, Any]: ...
    def __getstate__(self) -> None: ...
    def __init__(self, *args, **kwargs) -> None: ...
    def __new__(cls: __builtin__.type[`_Tnamedtuple-MemberInfo-module-member_name-member-type-module_path`], module, member_name, member, type, module_path) -> `_Tnamedtuple-MemberInfo-module-member_name-member-type-module_path`: ...
    def _asdict(self) -> collections.OrderedDict[str, Any]: ...
    @classmethod
    def _make(cls: __builtin__.type[`_Tnamedtuple-MemberInfo-module-member_name-member-type-module_path`], iterable: Iterable, new = ..., len: Callable[[Sized], int] = ...) -> `_Tnamedtuple-MemberInfo-module-member_name-member-type-module_path`: ...
    def _replace(self: `_Tnamedtuple-MemberInfo-module-member_name-member-type-module_path`, **kwds) -> `_Tnamedtuple-MemberInfo-module-member_name-member-type-module_path`: ...

def _is_public_func_or_class(name, member) -> bool: ...
def create_dataframe_summary_of_modules(modules) -> Any: ...
def get_module_infos_for_path(path, filter_list = ...) -> List[pkgutil.`namedtuple-ModuleInfo-0`]: ...
def load_modules_from_module_infos(module_infos) -> List[module]: ...
def namedtuple(typename: str, field_names: Union[str, Iterable[str]], *, verbose: bool = ..., rename: bool = ...) -> type: ...
