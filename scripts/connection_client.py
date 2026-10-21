# Built with boilerplate from: https://realpython.com/python-sockets/
import socket
import time


# Get IP address of device in LAN.
HOST: str = "127.0.0.1" #insert proper server IP address here.

# Port to listen on (non-privileged ports are > 1023)
PORT: int = 65432


# A fresh socket is created for every connection attempt (see poll_connection_state),
# because a socket that failed to connect cannot be reused.
connection_to_server_tcp: socket.socket | None = None


client_execution_state: int = 0


def _close_socket() -> None:
    global connection_to_server_tcp
    if connection_to_server_tcp is not None:
        try:
            connection_to_server_tcp.close()
        except OSError:
            pass
        connection_to_server_tcp = None


def _drop_connection() -> None:
    """The server went away: close the socket and go back to trying to connect."""
    global client_execution_state
    _close_socket()
    client_execution_state = 0


def client_close() -> None:
    """Close the connection. Safe to call repeatedly."""
    _close_socket()


def poll_connection_state() -> None:
    global connection_to_server_tcp, client_execution_state
    attempt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        attempt.settimeout(0.1)
        attempt.connect( (HOST, PORT) )
        # Set all methods to be non-blocking.
        # From this point on, all socket receiving methods behave like polling methods.
        attempt.setblocking(False)
        connection_to_server_tcp = attempt
        client_execution_state = 1
        pass
    except Exception as e:
        attempt.close()
        if isinstance(e, (BlockingIOError, TimeoutError, ConnectionError)):
            # Timeout / server not up yet is expected; try again next loop.
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
        if msg == b"":
            # An empty read means the server closed the connection.
            _drop_connection()
            msg = None
        pass
    except Exception as e:
        if isinstance(e, BlockingIOError):
            # Timeout is expected.
            pass
        elif isinstance(e, ConnectionError):
            # Server vanished (e.g. reset); go back to reconnecting.
            _drop_connection()
            pass
        else:
            # Cannot set up the connection.
            client_execution_state = -1
            pass
        pass
    return msg


def client_send_message(msg: bytes) -> None:
    global connection_to_server_tcp
    if connection_to_server_tcp is None:
        return
    try:
        connection_to_server_tcp.setblocking(True)
        connection_to_server_tcp.sendall(msg)
        connection_to_server_tcp.setblocking(False)
    except OSError:
        _drop_connection()
    pass


client_process_message_callbacks: set = set()

def client_process_message(msg: bytes | None) -> None:
    for callback in client_process_message_callbacks:
        callback(msg)
        pass
    pass


def client_execution_loop() -> float:
    global client_execution_state, connection_to_server_tcp
    match client_execution_state:
        case 0:
            poll_connection_state()
            pass
        case 1:
            client_process_message(client_poll_messages())
            pass
        case 2:
            client_close()
            return 0.0
        case _:
            client_close()
            return 0.0
    return 0.2







# Code to test functionality

if __name__ == "__main__":
    def print_message(msg: bytes | None) -> None:
        # Placeholder reaction code.
        if msg != None:
            print(msg.decode("utf-8"), end='')
            pass
        pass

    client_process_message_callbacks.add(print_message)

    counter = 1

    while client_execution_state in (0, 1):
        if client_execution_state == 1:
            # Connection is established.
            client_send_message("Hello Server! - {0}\n".format(counter).encode("utf-8"))
            counter += 1
            pass
        time.sleep(client_execution_loop())
        pass
    client_close()
