'''These are some simple CFG-parsing tests.

Given infinite time, we'd validate that correct values are generated - instead, we simply want to
ensure in this case that we construct a CFG without crashing as a bare-min.'''
# TODO: FIll in.
def test_async():
  source = 'result = [i async for i in aiter() if i % 2]'
  d = '{i:i for i in range(3) if i % 2 == 1 if True for j in range(3) if True}'
  a = 'async for a in foo(): pass' 