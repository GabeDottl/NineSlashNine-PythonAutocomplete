import asyncio
from jedi import debug
import argparse

@asyncio.coroutine
def handle_echo(reader, writer):
    data = yield from reader.readline()
    color = data.decode()[:-1]
    data = yield from reader.readline()
    msg = data.decode()[:-1]
    # haha. This method of message-handling is a textbook security nono...
    # "(color, message)"
    # color, msg = eval(color_message)
    debug.print_to_stdout(color, msg)

    # addr = writer.get_extra_info('peername')
    # print("Send: %r" % message)
    # writer.write(data)
    # yield from writer.drain()

    # print("Close the client socket")
    # writer.close()

if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('address')
  args = parser.parse_args()

  loop = asyncio.get_event_loop()
  coro = asyncio.start_server(handle_echo, args.address, 16262, loop=loop)
  server = loop.run_until_complete(coro)

  # Serve requests until Ctrl+C is pressed
  print('Listening for  on {}'.format(server.sockets[0].getsockname()))
  try:
      loop.run_forever()
  except KeyboardInterrupt:
      pass

  # Close the server
  server.close()
  loop.run_until_complete(server.wait_closed())
  loop.close()
