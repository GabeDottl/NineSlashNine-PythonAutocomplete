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

Sooo, parso takes a solid *12x* longer to parse things than the ast module on cfg.py. Fuck. In
retrospect, should've benchmarked that earlier on. Damnit. Well, c'est la vie. My initial rationale
essentially still stands - I'd need parso support for WIP files. Damnit though.
