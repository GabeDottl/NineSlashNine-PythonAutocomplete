# Storage Design
Storing python object abstractions (e.g. Modules, Classes, Functions) to avoid reparsing and
and analyzing the same code over to facilitate much more rapid analysis of high-level source files.

For example, if I create a module that imports something like Tensorflow, I certainly don't want
to have to import the tensorflow module with its vast array of submodule dependencies, which, even
with CPython takes a few seconds to import.

Instead, we want to do the bare minimum amount of work necessary, to get the information
we need as we need it.

Ideally, we take this to the extreme where we only import dependencies of dependencies as they're
needed or as they're convenient. For example, tf.Dataset may just be considered 'some type' until
we need to know more about the type (e.g. because we're retrieving some attribute from it).

Ultimately, one can imagine lots of amazing things to do here to really maximize the speed of
things, but practically, we just need things to be 'fast enough'. 

The system needs to be able to facilitate 'instant' results to a user for autocomplete.

Human percieved latency varies wildly. 100ms is a classic wisdom, but seems too slow. 30Hz
translates to happening every 33ms which seems like a more reasonable bound.
https://stackoverflow.com/questions/536300/what-is-the-shortest-perceivable-application-response-delay

So, minimally, we should be trying to import arbitrary symbols in <33ms. Really, it needs to be much
faster than this since we also need to do filtering and such.

Running some quick tests in a terminal playing with dicts:


    >>> d = {f'{i}': i for i in range(10000)}

    >>> %timeit d[f'{random.randint(0,9999)}']
    869 ns ± 1.67 ns per loop (mean ± std. dev. of 7 runs, 1000000 loops each)

    >>> %timeit str(f'{random.randint(0,9999)}')
    867 ns ± 3.55 ns per loop (mean ± std. dev. of 7 runs, 1000000 loops each)

    >>> %timeit d['1']
    24.9 ns ± 0.0082 ns per loop (mean ± std. dev. of 7 runs, 10000000 loops each)

    >>> d = {f'{i}': i for i in range(10000000)}

    >>> %timeit d[f'{random.randint(0,9999999)}']
    1.25 µs ± 10.9 ns per loop (mean ± std. dev. of 7 runs, 1000000 loops each)


    >>> %time d['2000']
    CPU times: user 4 µs, sys: 0 ns, total: 4 µs
    Wall time: 5.72 µs

    >>> %time d['20']
    CPU times: user 2 µs, sys: 0 ns, total: 2 µs
    Wall time: 3.81 µs

Reading a simple file ('hello'):


    >>> %time with open('./hello.txt') as f: f.readlines()
    CPU times: user 365 µs, sys: 8 µs, total: 373 µs
    Wall time: 414 µs

So, dict access is pretty fast - assuming the dict isn't hot, it seems reasonable to assume ~5us
lookups - which means room for ~6600 to reach 33ms.

## Options
# Pickle
- Loads of issues sharing across platform, poor practice generally.

# SQL database-options
- Overhead of database
- Requires structuring into an SQL-friendly format (modules = blobs?)

# Protobuf files
- Overhead of file-per-module
- Deserialization
- Requires convert to PB format

# Text files
- E.g. stubs
- Highly readable and debuggable
- Parsing raw text again

# HDF5, Feather, Arrow
http://matthewrocklin.com/blog/work/2015/03/16/Fast-Serialization
https://gist.github.com/gansanay/4514ec731da1a40d8811a2b3c313f836
HDF5 has a lot of use and seems to favor loading time over writing (which is the favoring we want).

    import h5py
    from autocomplete.code_understanding.typing import module_loader
    module = module_loader.load_module('autocomplete.code_understanding.typing.examples.storage_example', lazy=False)
    module_store = h5py.File('module_store.hdf5', 'w')
    module_group = module_store.create_group(module.name.replace('.', '/'))
    for key, value in module.get_members().items():
        value_dataset = module_group[key] = module_store.create_dataset(None, data=h5py.Empty('f'))
        value_dataset.attrs['type'] = str(type(value))

    >>> %time module_group['Klazz'].attrs['type']
    CPU times: user 463 µs, sys: 10 µs, total: 473 µs
    Wall time: 482 µs

    >>> %time module_group['Klazz']
    CPU times: user 339 µs, sys: 0 ns, total: 339 µs
    Wall time: 350 µs

    >>> %time module_group['Klazz']
    CPU times: user 362 µs, sys: 0 ns, total: 362 µs
    Wall time: 372 µs

    >>> %timeit module_group['Klazz']
    30.8 µs ± 77.9 ns per loop (mean ± std. dev. of 7 runs, 10000 loops each)

    >>> %time module_group['Klazz']
    CPU times: user 108 µs, sys: 3 µs, total: 111 µs
    Wall time: 114 µs

    >>> %time module_group['__file__']
    CPU times: user 220 µs, sys: 5 µs, total: 225 µs
    Wall time: 231 µs

Damn though, that's pretty heavy by comparison to dicts... Still, faster than loading modules our way:

    >>> %time module = module_loader.load_module('autocomplete.code_understanding.typing.examples.storage_example', lazy=False)                                                               CPU times: user 2.43 ms, sys: 0 ns, total: 2.43 ms
    Wall time: 2.33 ms

And much faster than loading modules the normal way; although, 2nd attempt
is unsuprisingly much faster:

    >>> %time importlib.import_module('autocomplete.code_understanding.typing.examples.storage_example')
    CPU times: user 71 ms, sys: 60.8 ms, total: 132 ms
    Wall time: 42.4 ms

    >>> %time importlib.import_module('autocomplete.code_understanding.typing.examples.storage_example')
    CPU times: user 22 µs, sys: 3 µs, total: 25 µs
    Wall time: 26.7 µs

Of course, this is far from an apples-to-apples comparison - in one case, we're actually doing some
processing and and initialization within modules, importing indirect dependencies, etc. In the
HDF5 case, we're essentially saving and restoring an already loaded module and not bringing in any
dependencies necessarily - merely keeping track of what things are referring to incase we need to
lazily load things.

The biggest issue with raw HDF5 is that it's a row-store storage format - e.g. for CSVs or
DataFrames - not an object serializer.

It seems as if we can largely work around this via attributes on Datasets and Groups in HDF5 - but


# Thrift, msgpack
https://www.benfrederickson.com/dont-pickle-your-data/

Pretty extensive overview of serializers performance:
https://github.com/eishay/jvm-serializers/wiki


    >>> d = {f'{i}': i for i in range(100000)}

    >>> with open('/tmp/tmp.msg', 'wb') as f:
          2     %time msgpack.dump(d, f)
    CPU times: user 9.46 ms, sys: 7.91 ms, total: 17.4 ms
    Wall time: 16.9 ms

    >>> with open('/tmp/tmp.msg', 'rb') as f:
          2     %time x  = msgpack.load(f)
    CPU times: user 8.23 ms, sys: 4.08 ms, total: 12.3 ms
    Wall time: 12.2 ms

    >>> d = {f'{i}': i for i in range(100)}

    >>> with open('/tmp/tmp.msg', 'wb') as f:
          2     %time msgpack.dump(d, f)
    CPU times: user 31 µs, sys: 0 ns, total: 31 µs
    Wall time: 32.7 µs

    >>> with open('/tmp/tmp.msg', 'rb') as f:
          2     %time x  = msgpack.load(f)
    CPU times: user 25 µs, sys: 1e+03 ns, total: 26 µs
    Wall time: 27.9 µs



## Primary Goals


## Secondary Goals
