# Built with boilerplate from: https://realpython.com/python-sockets/
import os
import socket
import time


# Get IP address of device in LAN.
HOST: str = "127.0.0.1" #socket.gethostbyname(socket.gethostname())

# Port to listen on (non-privileged ports are > 1023)
PORT: int = 65432


# Sockets are created by server_start() rather than at import time, so importing this module has no side effects.
server_tcp: socket.socket | None = None
connection_to_client_tcp: socket.socket | None = None
client_port: int = 0


server_execution_state: int = 0


def server_start() -> None:
    """Create the listening socket. Call once before server_execution_loop()."""
    global server_tcp, connection_to_client_tcp, server_execution_state
    server_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name != "nt":
        # On Windows SO_REUSEADDR would let a second socket bind a port that is already in use, so only set it elsewhere.
        server_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_tcp.bind( (HOST, PORT) )
        server_tcp.listen()
    except Exception:
        server_tcp.close()
        server_tcp = None
        raise

    # Set all methods to be non-blocking.
    # From this point on, all socket receiving methods behave like polling methods.
    server_tcp.setblocking(False)
    connection_to_client_tcp = None
    server_execution_state = 0


def _close_client() -> None:
    global connection_to_client_tcp
    if connection_to_client_tcp is not None:
        try:
            connection_to_client_tcp.close()
        except OSError:
            pass
        connection_to_client_tcp = None


def _drop_client() -> None:
    """The client went away: close its socket and go back to accepting connections."""
    global server_execution_state
    _close_client()
    server_execution_state = 0


def server_close() -> None:
    """Close the client connection and the listening socket. Safe to call repeatedly."""
    global server_tcp
    _close_client()
    if server_tcp is not None:
        try:
            server_tcp.close()
        except OSError:
            pass
        server_tcp = None


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
        if msg == b"":
            # An empty read means the client closed the connection.
            _drop_client()
            msg = None
        pass
    except Exception as e:
        if isinstance(e, BlockingIOError):
            # Timeout is expected.
            pass
        elif isinstance(e, ConnectionError):
            # Client vanished (e.g. reset); wait for a new one.
            _drop_client()
            pass
        else:
            # Cannot set up the connection.
            server_execution_state = -1
            pass
        pass
    return msg


def server_send_message(msg: bytes) -> None:
    global connection_to_client_tcp
    if connection_to_client_tcp is None:
        return
    try:
        connection_to_client_tcp.setblocking(True)
        connection_to_client_tcp.sendall(msg)
        connection_to_client_tcp.setblocking(False)
    except OSError:
        _drop_client()
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
            server_close()
            return 0.0
        case _:
            server_close()
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

    server_start()
    server_process_message_callbacks.add(print_message)

    counter = 1

    while server_execution_state in (0, 1):
        if server_execution_state == 1:
            # connection is established.
            server_send_message("Hello Client! - {0}\n".format(counter).encode("utf-8"))
            counter += 1
            pass
        time.sleep(server_execution_loop())
        pass
    server_close()
