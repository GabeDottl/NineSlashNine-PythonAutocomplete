# (generated with --quick)

from typing import Any

glob: module
os: module
re: module
tf: Any

class SimpleRegexAutocompleter:
    complete_corpus: str
    def __init__(self, path) -> None: ...
    def search(self, s) -> list: ...

def __getattr__(name) -> Any: ...
def time() -> float: ...
def wildcard_wrapper(s) -> str: ...
