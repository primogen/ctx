"""Threaded stdlib HTTP server helpers for ctx-monitor."""

from __future__ import annotations

import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, TypeVar


class MonitorServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._ctx_shutdown = threading.Event()
        self._ctx_mutations_enabled = True
        super().__init__(*args, **kwargs)

    def shutdown(self) -> None:
        self._ctx_shutdown.set()
        super().shutdown()

    def server_close(self) -> None:
        self._ctx_shutdown.set()
        super().server_close()

    def handle_error(self, request: Any, client_address: Any) -> None:
        exc_type, _, _ = sys.exc_info()
        if exc_type is not None and issubclass(
            exc_type,
            (BrokenPipeError, ConnectionAbortedError, ConnectionResetError),
        ):
            return
        super().handle_error(request, client_address)


HandlerT = TypeVar("HandlerT", bound=BaseHTTPRequestHandler)


def server_shutdown_requested(server: Any) -> bool:
    event = getattr(server, "_ctx_shutdown", None)
    return bool(event is not None and event.is_set())


def make_monitor_server(
    host: str,
    port: int,
    handler_cls: type[HandlerT],
    *,
    mutations_enabled: bool,
) -> MonitorServer:
    server = MonitorServer((host, port), handler_cls)
    server._ctx_mutations_enabled = mutations_enabled
    return server
