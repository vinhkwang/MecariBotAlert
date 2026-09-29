import socket

import pytest

from tests.conftest import NetworkAccessForbiddenError


def test_tcp_connect_is_forbidden() -> None:
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket,
        pytest.raises(NetworkAccessForbiddenError),
    ):
        tcp_socket.connect(("203.0.113.1", 443))


def test_unix_socketpair_still_works() -> None:
    sending_socket, receiving_socket = socket.socketpair()
    with sending_socket, receiving_socket:
        sending_socket.sendall(b"x")
        assert receiving_socket.recv(1) == b"x"
