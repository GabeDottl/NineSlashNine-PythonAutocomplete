https://www.markdownguide.org/basic-syntax/

# Architecture

WTF is this thing?

This library is a 'fuzzy' static analyzer for Python code which extracts useful information for 
dev tools. This includes inferred types, imported libraries, and general information from which 
atterns may be derived.

In essence, one could consider this a VM within a (actual Python) VM. However, unlike running the code in reality, this library merely runs over the code performing a sort of lazy evaluation. It's linear in the number of lines compared to running the actual code which can have arbitrary performance.

Overview of Python's execution from parsing to AST to CFG to running byte code:
https://dev.to/btaskaya/lifecycle-of-a-python-code---cpythons-execution-model-85i

Design of the CPython compiler:
https://devguide.python.org/compiler/

Stacks and frames:
https://tech.blog.aknin.name/2010/07/22/pythons-innards-interpreter-stacks/

Essentially, we follow a similar process to the Python compiler but have a sort of hybrid AST/CFG. There are a few reasons for this:
1) Simplicity - we use the parso syntax tree as the AST essentially instead.
2) Weird execution model - we're not *really* trying to execute the code we're writing - merely
gleam useful information from it.
3) Unlike Python, we'll 'execute' inspite of =+
...

## Why
1) Need to process Python code anyway
2) Platform for suggesting edits (parso mapping provides code entry-points)
3) Type information inspite of ambiguity

This would not need to exist for a statically typed language. In essence, one could consider this as more of a type compiler.

## Overview
### Part 1: Parsing
Parsing is done with the [parso](https://github.com/davidhalter/parso) library, which was originally created for `jedi`, and which handles broken syntax well. It creates a parse tree of sorts, but not the AST we'd love.

The other alternative would be Python's builtin `ast` module, which has a friendlier API (operating in terms of higher-level concepts like function calls), but breaks completely on any broken syntax - which means it would not be usable for working on actively modified source which is naturally broken most of the time.

### Part 2: Control Flow Graph
The parso graph is transformed into a control flow graph composed of `CfgNode`s. These nodes define `process` methods which will fuzzily execute the graph within some frame.


### Part 3: Execution
Graph is executed, things are stored in a Frame.

### Part 4: Finish Execution
Unexecuted functions (e.g. public ones) are executed.

### Part 5: Analysis
The Collector 

# Assumptions
Python's painfully flexible and it is this flexibility which essentially makes analysis so 
difficult in the first place. 

## Call order independence
Too exhausting to figure out the order in which things must be called

## APIs won't be changed externally (i.e. no monkey-typing?)
Assume all attributes are defined within the 

Assume no one's going to do something like:


    np.x = min

Redfining public APIs is just downright obnoxious. Doing this with your own modules and objects also just makes things confusing. We essentially assume that all atr

# Tricks
To infer more types than we can strongly, we rely on a few tricks.

## Similarly named things may be the same thing
If a name X is used commonly (e.g. 'node') in a given module, it is likely that all variables of
this name refer to the type. So, if node is assigned to a concrete type in some location, we can
use that as a hint that it is the same type in all other locations.

## When there's ambiguity, prefer local definitions
Similar to common path resolution rules, we prefer inferring local types. For the `node` example, 
there are of course many sorts of types this could correspond to many things (`CfgNode`, `parso.Node`, `ast.Node`, etc.), but in the absence of other hints, we'd prefer whatever's been imported in this module followed by whatever's defined nearby, followed by whatever's most likely based on the current context (ideally - more practically, popularity?)

## Usage of names provides evidence
If I have a parameter `x` and we invoke attributes on it `foo` and `bar`, then the type of `x` is likely to have these attributes. Alternatively, if we're doing `isinstance` checks, that's also strong evidence (and a guarantee generally).

# Core Philosophy
## Break Gracefully
Python's an evolving language and people often use it in strange, unexpected ways. For this reason, we have to assume that we're going to run into unexpected syntax or logic and always handle it in some reasonable way. We do not, for example, want to complete choke on some new grammar introduced ([ala rope and type hints](https://github.com/python-rope/rope/issues/254)].

## Make it clear when we're guessing
Because of Python's duck-typing system, one is often guessing at values based on context. When this is the case, we try to make this explicit - since we may be wrong.

TODO: Manifest this as one or more question marks (?,??,???) next to a type name when giving hints.

## Match Python's standard model where possible
Where possible, we strive to use the same terminology used by Python and the same sort of
concepts - e.g. Expressions, Statments, Frames, globals, locals, etc. Further, we try to vaguely
follow the same logic flow and match Python proper wherever possible.
'