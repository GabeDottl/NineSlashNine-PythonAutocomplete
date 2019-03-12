import asyncio

@asyncio.coroutine
def tcp_echo_client(message, loop, address='localhost'):
    reader, writer = yield from asyncio.open_connection(address, 16261,
                                                        loop=loop)
    # print('Send: %r' % message)
    writer.write(message.encode())
    #
    # data = yield from reader.read(100)
    # print('Received: %r' % data.decode())

    # print('Close the socket')
    writer.close()


def echo(color, msg, address='localhost', *args):
  loop = asyncio.get_event_loop()
  # Replace " with ' to make compatible with our string-encoded string-tuple.
  color = color.replace('"', "'")
  msg = msg.replace('"', "'")
  loop.run_until_complete(tcp_echo_client(f'("{color}", "{msg}")', loop, address=address))
