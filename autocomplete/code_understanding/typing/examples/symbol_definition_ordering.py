from typing import (Any, Callable, Dict, Generic, List, Mapping, Optional,
                    Sequence, Tuple, Type, TypeVar, Union, overload)

_T = TypeVar("_T")

_ValidatorType = Callable[[Any, Attribute[_T], _T], Any]


class Attribute:
  pass
