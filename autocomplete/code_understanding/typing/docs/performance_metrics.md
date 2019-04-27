# Interesting measures
As of 4/26/19:

    >>> with open('/home/gabe/code/autocomplete/autocomplete/code_understanding/typing/control_flow_graph.py') as f:
               source = ''.join(f.readlines())
    >>> %time ast.parse(source)
        %time parso.parse(source)
        %time graph = api.graph_from_source(source)
    CPU times: user 3.08 ms, sys: 0 ns, total: 3.08 ms
    Wall time: 3.08 ms
    CPU times: user 38.3 ms, sys: 0 ns, total: 38.3 ms
    Wall time: 37.9 ms
    CPU times: user 43.6 ms, sys: 3.79 ms, total: 47.4 ms
    Wall time: 47.3 ms

    >>> from typed_ast import ast3
    >>> %time ast3.parse(source)
    CPU times: user 5.55 ms, sys: 51 µs, total: 5.6 ms
    Wall time: 5.67 ms


Sooo, parso takes a solid *12x* longer to parse things than the ast module on cfg.py. Fuck. In
retrospect, should've benchmarked that earlier on. Damnit. Well, c'est la vie. My initial rationale
essentially still stands - I'd need parso support for WIP files. Damnit though.

typed_ast seems like a nice balance - still fast (only ~2x slower than ast proper) and it supports
types.

# Loading control_flow_graph.py

    >>>
    import cProfile
    from autocomplete.code_understanding.typing import module_loader
    module_name = 'autocomplete.code_understanding.typing.control_flow_graph'
    cProfile.runctx('module_loader.load_module(module_name, lazy=False)', globals(), locals(), filename='cfg_py_stats')
    import pstats
    from pstats import SortKey
    p.strip_dirs().sort_stats(SortKey.TIME).print_stats(100)

      ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      222146    1.181    0.000    2.906    0.000 parser.py:168(_add_token)
      998396    0.591    0.000    1.089    0.000 parser.py:200(_pop)
      222233    0.576    0.000    1.106    0.000 tokenize.py:351(tokenize_lines)
      241686    0.263    0.000    0.263    0.000 {method 'match' of 're.Pattern' objects}
    175182/31975    0.208    0.000    0.503    0.000 tree.py:272(_get_code_for_children)
        20308    0.199    0.000    0.211    0.000 _make.py:2062(__call__)
      107019    0.197    0.000    0.298    0.000 parser.py:84(convert_node)
      998483    0.184    0.000    0.184    0.000 parser.py:75(__init__)
    808522/794859    0.160    0.000    0.341    0.000 {built-in method builtins.isinstance}
      222146    0.150    0.000    0.306    0.000 parser.py:112(convert_leaf)
      581/559    0.148    0.000    0.511    0.001 language_objects.py:267(new)
      2311661    0.144    0.000    0.144    0.000 {method 'append' of 'list' objects}
        8504    0.126    0.000    0.384    0.000 parsing_utils.py:39(variables_from_node)
    261038/87    0.119    0.000    1.807    0.021 parsing_utils.py:28(inner_wrapper)
    647364/125522    0.114    0.000    0.374    0.000 tree.py:274(<genexpr>)
    179152/35945    0.103    0.000    0.398    0.000 {method 'join' of 'str' objects}
      222146    0.097    0.000    0.141    0.000 tree.py:170(__init__)
          87    0.094    0.001    4.184    0.048 parser.py:123(parse)
      1051622    0.085    0.000    0.085    0.000 {method 'pop' of 'list' objects}
      559412    0.084    0.000    0.084    0.000 {built-in method _abc._abc_instancecheck}
      559412    0.078    0.000    0.163    0.000 abc.py:137(__instancecheck__)
      222233    0.077    0.000    1.183    0.000 parser.py:204(_recovery_tokenize)
    74114/87    0.076    0.000    1.807    0.021 control_flow_graph.py:82(_create_cfg_node)
    1123690/1116064    0.072    0.000    0.074    0.000 {built-in method builtins.len}
      222146    0.071    0.000    0.071    0.000 parser.py:87(_token_to_transition)
      445151    0.058    0.000    0.058    0.000 {method 'group' of 're.Match' objects}
    71445/27593    0.058    0.000    0.459    0.000 parsing_utils.py:434(expression_from_node)

From cumulative time we can see:
     227/1    0.000    0.000    6.814    6.814 module_loader.py:234(load_module)
    ...
      87    0.000    0.000    4.198    0.048 __init__.py:49(parse)
    ...

So, parsing is taking up a solid ~2/3rds of the time.
