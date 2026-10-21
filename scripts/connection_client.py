# Built with boilerplate from: https://realpython.com/python-sockets/
import socket


# Get IP address of device in LAN.
HOST: str = "127.0.0.1" #insert proper server IP address here.

# Port to listen on (non-privileged ports are > 1023)
PORT: int = 65432


connection_to_server_tcp: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Set all methods to be non-blocking.
# From this point on, all socket receiving methods behave like polling methods.
connection_to_server_tcp.setblocking(False)


client_execution_state: int = 0


def poll_connection_state() -> None:
    global connection_to_server_tcp, client_execution_state
    try:
        connection_to_server_tcp.setblocking(True)
        connection_to_server_tcp.settimeout(0.1)
        connection_to_server_tcp.connect( (HOST, PORT) )
        connection_to_server_tcp.settimeout(None)
        connection_to_server_tcp.setblocking(False)
        client_execution_state = 1
        pass
    except Exception as e:
        if isinstance(e, BlockingIOError) or isinstance(e, TimeoutError):
            connection_to_server_tcp.close()
            # Timeout is expected.
            pass
        else:
            # Cannot set up the connection.
            client_execution_state = -1
            pass
        pass
    pass


def client_poll_messages() -> bytes | None:
    global client_execution_state, connection_to_server_tcp
    msg: bytes = None
    try:
        msg = connection_to_server_tcp.recv(1024)
        pass
    except Exception as e:
        if isinstance(e, BlockingIOError):
            # Timeout is expected.
            pass
        else:
            # Cannot set up the connection.
            client_execution_state = -1
            pass
        pass
    return msg


def client_send_message(msg: bytes) -> None:
    global connection_to_server_tcp
    connection_to_server_tcp.setblocking(True)
    connection_to_server_tcp.send(msg)
    connection_to_server_tcp.setblocking(False)
    pass


client_process_message_callbacks: set = set()

def client_process_message(msg: bytes | None) -> None:
    for callback in client_process_message_callbacks:
        callback(msg)
        pass
    pass


def client_execution_loop() -> float:
    global client_execution_state, connection_to_server_tcp, connection_to_server_tcp
    match client_execution_state:
        case 0:
            poll_connection_state()
            pass
        case 1:
            client_process_message(client_poll_messages())
            pass
        case 2:
            connection_to_server_tcp.close()
            connection_to_server_tcp.close()
            return 0.0
        case _:
            connection_to_server_tcp.close()
            return 0.0
    return 0.2







# Code to test functionality

def print_message(msg: bytes | None) -> None:
    # Placeholder reaction code.
    if msg != None:
        print(msg.decode("utf-8"), end='')
        pass
    pass

client_process_message_callbacks.add(print_message)

counter = 1

while client_execution_state == 0:
    client_execution_loop()
    pass
while client_execution_state == 1:
    # Connection is established.
    client_send_message("Hello Server! - {0}\n".format(counter).encode("utf-8"))
    counter += 1
    client_execution_loop()
    pass
