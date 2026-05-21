"""Build real adafruit_httpserver requests and assert on response objects."""

from __future__ import annotations

import socket
import threading
import time
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from adafruit_httpserver import Request, Server
from adafruit_httpserver.response import JSONResponse, Response

from esp_remote.firmware.uart_buffer import UartBuffer
from esp_remote.firmware.web_terminal import WebTerminal

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = REPO_ROOT / "static"


class MockUart:
    """Minimal UART stand-in for handler tests."""

    def __init__(self, *, pending: bytes = b"") -> None:
        self._pending = pending
        self.written: list[bytes] = []

    @property
    def in_waiting(self) -> int:
        return len(self._pending)

    def read(self, size: int) -> bytes:
        chunk = self._pending[:size]
        self._pending = self._pending[size:]
        return chunk

    def write(self, data: bytes) -> None:
        self.written.append(data)


class FailingUart(MockUart):
    """UART that raises OSError on access (simulates hardware faults)."""

    @property
    def in_waiting(self) -> int:
        raise OSError("uart unavailable")


def build_request(
    server: Server,
    method: str,
    path: str,
    *,
    body: bytes = b"",
    extra_headers: dict[str, str] | None = None,
) -> Request:
    """Construct a parsed ``Request`` matching what the server receives on the wire."""
    headers = ["Host: test", f"Content-Length: {len(body)}"]
    if body and (extra_headers is None or "Content-Type" not in extra_headers):
        headers.append("Content-Type: application/x-www-form-urlencoded")
    if extra_headers:
        for key, value in extra_headers.items():
            headers.append(f"{key}: {value}")
    header_block = "\r\n".join(headers)
    raw = f"{method} {path} HTTP/1.1\r\n{header_block}\r\n\r\n".encode() + body
    return Request(server, MagicMock(), ("127.0.0.1", 4242), raw_request=raw)


def response_status(response: Response) -> int:
    return response._status.code


def response_text_body(response: Response) -> str:
    body = response._body
    if isinstance(body, bytes):
        return body.decode("utf-8")
    return body


def response_header(response: Response, name: str) -> str | None:
    return response._headers.get(name)


def json_payload(response: JSONResponse) -> dict[str, Any]:
    return response._data


def naive_login_password(body: str) -> str:
    """Old broken parser — kept to prove regression tests catch it."""
    if "password=" not in body:
        return ""
    value = body.split("password=", 1)[1].split("&", 1)[0]
    return value.replace("+", " ").strip()


def make_terminal_server(
    static_dir: Path = STATIC_DIR,
    *,
    uart: MockUart | None = None,
    rx_buffer: UartBuffer | None = None,
    stats=None,
) -> tuple[Server, WebTerminal, MockUart, UartBuffer]:
    uart = uart or MockUart()
    rx_buffer = rx_buffer or UartBuffer()
    server = Server(socket, str(static_dir), debug=False)
    terminal = WebTerminal(uart, rx_buffer, stats=stats)
    terminal.register(server)
    return server, terminal, uart, rx_buffer


class LiveServer:
    """Background poll loop around a real bound httpserver socket."""

    def __init__(self, server: Server) -> None:
        self.server = server
        self._bound_port: int | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self.server.poll()
            time.sleep(0.005)

    def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        self.server.start(host, port)
        self._bound_port = int(self.server._sock.getsockname()[1])
        self._thread.start()
        time.sleep(0.05)
        return self._bound_port

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self.server.stop()
        self._bound_port = None

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        if self._bound_port is None:
            raise RuntimeError("call start() before request()")
        conn = HTTPConnection("127.0.0.1", self._bound_port, timeout=3)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        raw_headers = {k.lower(): v for k, v in response.getheaders()}
        payload = response.read()
        conn.close()
        return response.status, raw_headers, payload
