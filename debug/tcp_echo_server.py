import asyncio
from jedi import debug

@asyncio.coroutine
def handle_echo(reader, writer):
    data = yield from reader.read(100)
    color_message = data.decode()
    # addr = writer.get_extra_info('peername')
    # haha. This is color_message a textbook security nono...
    # "(color, message)"
    color, msg = eval(color_message)
    debug.print_to_stdout(color, msg)
    # print("Received %r from %r" % (message, addr))

    # print("Send: %r" % message)
    # writer.write(data)
    # yield from writer.drain()

    # print("Close the client socket")
    # writer.close()

loop = asyncio.get_event_loop()
coro = asyncio.start_server(handle_echo, '127.0.0.1', 16261, loop=loop)
server = loop.run_until_complete(coro)

# Serve requests until Ctrl+C is pressed
print('Serving on {}'.format(server.sockets[0].getsockname()))
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass

# Close the server
server.close()
loop.run_until_complete(server.wait_closed())
loop.close()
