https://www.markdownguide.org/basic-syntax/

# Architecture

WTF is this thing?

This library is a 'fuzzy' static analyzer for Python code which extracts useful information for dev
tools. This includes inferred types, imported libraries, and general information from which patterns
may be derived.

## Overview
### Part 1: Parsing
Parsing is done with the `parso` library, which was originally created for `jedi`, and which handles broken syntax well. Unfortunately, it is a relatively direct parsing of the python grammar.

The other alternative would be Python's builtin `ast` module, which has a friendlier API (operating in terms of higher-level concepts like function calls), but breaks completely on any broken syntax - which means it would not be usable for working on actively modified source which is naturally broken most of the time.

### Part 2: Control Flow Graph
The parso graph is transformed into a control flow graph composed of `CfgNode`s. These nodes define `process` methods which will fuzzily execute the graph within some frame.


### Part 3: Execution
Graph is executed, things are stored in a Frame.

### Part 4: Finish Execution
Unexecuted functions (e.g. public ones) are executed.

### Part 5: Analysis
The Collector 