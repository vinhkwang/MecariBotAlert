import socket
from collections.abc import Callable

import pytest


class NetworkAccessForbiddenError(RuntimeError):
    pass


def guard_socket_method[**P, R](
    original_method: Callable[P, R],
) -> Callable[P, R]:
    def guarded_method(*args: P.args, **kwargs: P.kwargs) -> R:
        connecting_socket = args[0]
        if (
            isinstance(connecting_socket, socket.socket)
            and connecting_socket.family != socket.AF_UNIX
        ):
            raise NetworkAccessForbiddenError(
                f"tests must not open network connections: {args[1:]}"
            )
        return original_method(*args, **kwargs)

    return guarded_method


@pytest.fixture(autouse=True)
def forbid_network_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", guard_socket_method(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard_socket_method(socket.socket.connect_ex))
