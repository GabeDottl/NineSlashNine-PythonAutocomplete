# (generated with --quick)

from typing import Any, Dict, List, TextIO, Tuple

argparse: module
args: argparse.Namespace
drawer: ParsoDrawer
f: TextIO
graphviz: Any
parser: argparse.ArgumentParser
parso: Any
source: str
tree: Any
webbrowser: module

class ParsoDrawer:
    graph: Any
    line_to_nodes: Dict[Any, List[Tuple[Any, Any]]]
    parent: Any
    parent_lineno: Any
    def __init__(self, path = ...) -> None: ...
    def create_graph(self, source, include_source = ...) -> None: ...
    def traverse(self, node) -> None: ...
