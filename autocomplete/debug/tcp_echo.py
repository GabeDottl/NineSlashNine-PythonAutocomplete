import asyncio

@asyncio.coroutine
def tcp_echo_client(color, msg, loop, address='localhost'):
    reader, writer = yield from asyncio.open_connection(address, 16261,
                                                        loop=loop)
    # print('Send: %r' % msg)
    writer.write(color.encode())
    writer.write(msg.encode())
    #
    # data = yield from reader.read(100)
    # print('Received: %r' % data.decode())

    # print('Close the socket')
    writer.close()

def _new_loop():
  loop = asyncio.new_event_loop()
  asyncio.set_event_loop(loop)
  return loop

def echo(color, msg, address='localhost', *args):
  try:
    loop = asyncio.get_event_loop()
  except Exception as e:
    loop = _new_loop()
  except Error as e:
    loop = _new_loop()
  # eplace " with ' to make compatible with our string-encoded string-tuple.
  # color = color.replace('"', "'")
  # msg = str(msg)
  # msg = msg.replace('"', "'")
  color.replace('\n', '\t')
  color = color + '\n'
  msg.replace('\n', '\t')
  msg = msg +'\n'

  loop.run_until_complete(tcp_echo_client(color, msg, loop, address=address))
