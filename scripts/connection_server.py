# Built with boilerplate from: https://realpython.com/python-sockets/
import socket


# Get IP address of device in LAN.
HOST: str = "127.0.0.1" #socket.gethostbyname(socket.gethostname())

# Port to listen on (non-privileged ports are > 1023)
PORT: int = 65432


server_tcp: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_tcp.bind( (HOST, PORT) )
server_tcp.listen()

# Set all methods to be non-blocking.
# From this point on, all socket receiving methods behave like polling methods.
server_tcp.setblocking(False)

connection_to_client_tcp: socket.socket = None
client_port: int = 0


server_execution_state: int = 0


def poll_connection_request() -> None:
    global connection_to_client_tcp, client_port, server_execution_state
    try:
        connection_to_client_tcp, client_port = server_tcp.accept()
        connection_to_client_tcp.setblocking(False)
        server_execution_state = 1
        pass
    except Exception as e:
        if isinstance(e, BlockingIOError):
            # Timeout is expected.
            pass
        else:
            # Cannot set up the connection.
            server_execution_state = -1
            pass
        pass
    pass


def server_poll_messages() -> bytes | None:
    global server_execution_state, connection_to_client_tcp
    msg: bytes = None
    try:
        msg = connection_to_client_tcp.recv(1024)
        pass
    except Exception as e:
        if isinstance(e, BlockingIOError):
            # Timeout is expected.
            pass
        else:
            # Cannot set up the connection.
            server_execution_state = -1
            pass
        pass
    return msg


def server_send_message(msg: bytes) -> None:
    global connection_to_client_tcp
    connection_to_client_tcp.setblocking(True)
    connection_to_client_tcp.send(msg)
    connection_to_client_tcp.setblocking(False)
    pass


server_process_message_callbacks: set = set()

def server_process_message(msg: bytes | None) -> None:
    for callback in server_process_message_callbacks:
        callback(msg)
        pass
    pass


def server_execution_loop() -> float:
    global server_execution_state, connection_to_client_tcp, server_tcp
    match server_execution_state:
        case 0:
            poll_connection_request()
            pass
        case 1:
            server_process_message(server_poll_messages())
            pass
        case 2:
            connection_to_client_tcp.close()
            server_tcp.close()
            return 0.0
        case _:
            server_tcp.close()
            return 0.0
    return 0.2






# Code to test functionality

def print_message(msg: bytes | None) -> None:
    # Placeholder reaction code.
    if msg != None:
        print(msg.decode("utf-8"), end='')
        pass
    pass

server_process_message_callbacks.add(print_message)

counter = 1

while server_execution_state == 0:
    server_execution_loop()
    pass
while server_execution_state == 1:
    # connection is established.
    server_send_message("Hello Client! - {0}\n".format(counter).encode("utf-8"))
    counter += 1
    server_execution_loop()
    pass
