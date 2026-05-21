"""HTTP web terminal on the ESP32 (login + UART poll API)."""

import os

from esp_remote.firmware.form_parse import bytes_to_text, parse_form_urlencoded
from esp_remote.firmware.session import (
    authorized,
    cookie_present,
    end_session,
    login_set_cookie_header,
    logout_clear_cookie_header,
    start_session,
)
from esp_remote.firmware.uart_buffer import GAP_NOTICE
from esp_remote.firmware.uart_pi import int_setting

# Sent to Pi serial on logout (shell exit; harmless at login prompt).
_LOGOUT_UART = b"\r\nexit\r\n"

_UART_CHUNK = 256
_UART_TX_CHUNK = 64
_HTTP_UNAUTHORIZED = (401, "Unauthorized")


def _password() -> str:
    return os.getenv("WEB_PASSWORD", "") or os.getenv("CIRCUITPY_WEB_API_PASSWORD", "")


def login_password_from_body(body: str) -> str:
    """Password field from a browser POST (application/x-www-form-urlencoded)."""
    return parse_form_urlencoded(body).get("password", "").strip()


def passwords_match(expected: str, submitted: str) -> bool:
    """True when auth is disabled (empty expected) or passwords match."""
    expected = expected.strip()
    submitted = submitted.strip()
    return not expected or submitted == expected


class WebTerminal:
    """Route handlers for the browser terminal and UART poll API."""

    def __init__(self, uart, rx_buffer, stats=None) -> None:
        self._uart = uart
        self._rx_buffer = rx_buffer
        self._stats = stats

    def _poll_uart(self) -> None:
        try:
            waiting = self._uart.in_waiting
            if waiting:
                chunk = self._uart.read(min(waiting, _UART_CHUNK))
                if chunk:
                    self._rx_buffer.append(chunk)
                    if self._stats is not None:
                        self._stats.record_rx(len(chunk))
        except OSError as exc:
            print(f"uart read: {exc}")
            if self._stats is not None:
                self._stats.record_read_error()

    def _uart_pending(self) -> int:
        try:
            return int(self._uart.in_waiting or 0)
        except OSError:
            return 0

    def login(self, request):
        from adafruit_httpserver import Redirect, Response  # noqa: PLC0415

        expected = _password()
        submitted = login_password_from_body(request.body.decode("utf-8"))
        if not passwords_match(expected, submitted):
            return Response(
                request,
                body="<!DOCTYPE html><html><body><p>Invalid password. "
                '<a href="/">Try again</a></p></body></html>',
                status=_HTTP_UNAUTHORIZED,
                content_type="text/html",
            )
        start_session()
        return Redirect(
            request,
            "/terminal.html",
            headers=login_set_cookie_header(),
        )

    def api_output(self, request):
        from adafruit_httpserver import JSONResponse, Response  # noqa: PLC0415

        if not authorized(request):
            return Response(request, body="Unauthorized", status=_HTTP_UNAUTHORIZED)
        self._poll_uart()
        since = int(request.query_params.get("since", "0") or "0")
        chunk, cursor, gap = self._rx_buffer.read_since(since)
        if gap and chunk:
            chunk = GAP_NOTICE + chunk
        text = bytes_to_text(chunk)
        pending = self._rx_buffer.total_rx - cursor
        return JSONResponse(
            request,
            {"data": text, "since": cursor, "pending": pending},
        )

    def api_input(self, request):
        from adafruit_httpserver import JSONResponse, Response  # noqa: PLC0415

        if not authorized(request):
            return Response(request, body="Unauthorized", status=_HTTP_UNAUTHORIZED)
        data = request.body
        if data:
            self._write_uart(data)
        return JSONResponse(request, {"ok": True, "bytes": len(data)})

    def _write_uart(self, data: bytes) -> None:
        """Write in small chunks so a large paste does not block the HTTP server."""
        length = len(data)
        if length <= _UART_TX_CHUNK:
            self._uart.write(data)
            if self._stats is not None:
                self._stats.record_tx(length)
            return
        offset = 0
        while offset < length:
            piece = data[offset : offset + _UART_TX_CHUNK]
            self._uart.write(piece)
            if self._stats is not None:
                self._stats.record_tx(len(piece))
            offset += _UART_TX_CHUNK

    def api_status(self, request):
        from adafruit_httpserver import JSONResponse, Response  # noqa: PLC0415

        if not authorized(request):
            return Response(request, body="Unauthorized", status=_HTTP_UNAUTHORIZED)
        self._poll_uart()
        payload = {
            "buffer_bytes": len(self._rx_buffer),
            "rx_total": self._rx_buffer.total_rx,
            "tx_total": self._stats.tx_bytes if self._stats else 0,
            "uart_pending": self._uart_pending(),
            "baud": int_setting("PI_UART_BAUD", 115200),
            "read_errors": self._stats.read_errors if self._stats else 0,
        }
        return JSONResponse(request, payload)

    def logout(self, request):
        from adafruit_httpserver import JSONResponse, Redirect  # noqa: PLC0415

        if cookie_present(request):
            self._write_uart(_LOGOUT_UART)
        end_session()
        headers = logout_clear_cookie_header()
        # Prefer JSON for fetch from terminal.js; redirect works for direct navigation.
        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            return JSONResponse(request, {"ok": True}, headers=headers)
        return Redirect(request, "/login.html", headers=headers)

    def index(self, request):
        from adafruit_httpserver import Redirect  # noqa: PLC0415

        if authorized(request):
            return Redirect(request, "/terminal.html")
        return Redirect(request, "/login.html")

    def register(self, server) -> None:
        """Attach routes to an adafruit_httpserver ``Server``."""
        server.route("/login", "POST")(self.login)
        server.route("/logout", "POST")(self.logout)
        server.route("/api/output", "GET")(self.api_output)
        server.route("/api/input", "POST")(self.api_input)
        server.route("/api/status", "GET")(self.api_status)
        server.route("/")(self.index)


def create_server(pool, uart, rx_buffer, root_path: str = "/static", stats=None):
    from adafruit_httpserver import Server  # noqa: PLC0415

    web_port = int(os.getenv("WEB_PORT") or "8080")
    server = Server(pool, root_path, debug=False)
    WebTerminal(uart, rx_buffer, stats=stats).register(server)
    print(f"web: listening on port {web_port}")
    server.start(host="0.0.0.0", port=web_port)
    return server
