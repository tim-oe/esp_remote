"""HTTP handler and integration tests using real adafruit_httpserver."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from adafruit_httpserver.response import JSONResponse, Redirect

from esp_remote.firmware.session import AUTH_COOKIE
from esp_remote.firmware.uart_buffer import UartBuffer
from esp_remote.firmware.uart_stats import UartStats
from esp_remote.firmware.web_terminal import (
    _password,
    create_server,
    login_password_from_body,
    passwords_match,
)
from tests.httpserver_test_utils import (
    FailingUart,
    LiveServer,
    build_request,
    json_payload,
    make_terminal_server,
    naive_login_password,
    response_header,
    response_status,
    response_text_body,
)

_BROWSER_LOGIN_BODY = "password=test%40pwd"
_EXPECTED_PASSWORD = "test@pwd"


@pytest.fixture
def web_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_PASSWORD", _EXPECTED_PASSWORD)
    monkeypatch.delenv("CIRCUITPY_WEB_API_PASSWORD", raising=False)


@pytest.fixture
def terminal(web_password: None) -> tuple:
    return make_terminal_server()


class TestLoginRegression:
    def test_naive_split_parser_does_not_decode_at_sign(self) -> None:
        """Documents the production bug: raw ``%40`` must not be compared to ``@``."""
        assert naive_login_password(_BROWSER_LOGIN_BODY) == "test%40pwd"
        assert naive_login_password(_BROWSER_LOGIN_BODY) != _EXPECTED_PASSWORD

    def test_real_parser_matches_browser_encoding(self) -> None:
        assert login_password_from_body(_BROWSER_LOGIN_BODY) == _EXPECTED_PASSWORD
        assert passwords_match(
            _EXPECTED_PASSWORD, login_password_from_body(_BROWSER_LOGIN_BODY)
        )


class TestLoginHandler:
    def test_wrong_password_returns_401_and_error_page(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, _uart, _buf = terminal
        request = build_request(server, "POST", "/login", body=b"password=wrong")
        response = web.login(request)
        assert response_status(response) == 401
        assert "Invalid password" in response_text_body(response)

    def test_correct_urlencoded_password_redirects_to_terminal(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, _uart, _buf = terminal
        request = build_request(
            server,
            "POST",
            "/login",
            body=_BROWSER_LOGIN_BODY.encode(),
        )
        response = web.login(request)
        assert isinstance(response, Redirect)
        assert response_status(response) == 302
        assert response_header(response, "Location") == "/terminal.html"
        cookie = response_header(response, "Set-Cookie") or ""
        assert AUTH_COOKIE in cookie
        assert "HttpOnly" in cookie

    def test_plus_in_password_is_decoded(
        self, terminal: tuple, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEB_PASSWORD", "ab+cd")
        server, web, _, _ = terminal
        request = build_request(server, "POST", "/login", body=b"password=ab%2Bcd")
        response = web.login(request)
        assert isinstance(response, Redirect)


class TestIndexHandler:
    def test_unauthenticated_redirects_to_login(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, _, _ = terminal
        response = web.index(build_request(server, "GET", "/"))
        assert isinstance(response, Redirect)
        assert response_header(response, "Location") == "/login.html"

    def test_authenticated_redirects_to_terminal(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, _, _ = terminal
        response = web.index(
            build_request(
                server,
                "GET",
                "/",
                extra_headers={"Cookie": AUTH_COOKIE},
            )
        )
        assert response_header(response, "Location") == "/terminal.html"


class TestApiHandlers:
    def test_api_output_without_cookie_returns_401(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, _, _ = terminal
        response = web.api_output(build_request(server, "GET", "/api/output"))
        assert response_status(response) == 401
        assert response_text_body(response) == "Unauthorized"

    def test_api_output_returns_uart_data_json(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, uart, buf = terminal
        uart._pending = b"pi login:"
        buf.append(b"cached")
        request = build_request(
            server,
            "GET",
            "/api/output?since=0",
            extra_headers={"Cookie": AUTH_COOKIE},
        )
        response = web.api_output(request)
        assert isinstance(response, JSONResponse)
        payload = json_payload(response)
        assert payload["data"] == "cachedpi login:"
        assert payload["since"] == buf.total_rx
        assert payload["pending"] == 0

    def test_api_input_writes_uart_and_returns_ok(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, uart, _ = terminal
        body = b"ls\r\n"
        request = build_request(
            server,
            "POST",
            "/api/input",
            body=body,
            extra_headers={
                "Cookie": AUTH_COOKIE,
                "Content-Type": "text/plain",
            },
        )
        response = web.api_input(request)
        assert json_payload(response) == {"ok": True, "bytes": 4}
        assert uart.written == [body]

    def test_api_input_without_auth_is_401(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, uart, _ = terminal
        web.api_input(build_request(server, "POST", "/api/input", body=b"x"))
        assert uart.written == []

    def test_api_status_reports_buffer_and_uart_counters(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, uart, buf = terminal
        buf.append(b"hello")
        request = build_request(
            server,
            "GET",
            "/api/status",
            extra_headers={"Cookie": AUTH_COOKIE},
        )
        response = web.api_status(request)
        payload = json_payload(response)
        assert payload["buffer_bytes"] == 5
        assert payload["rx_total"] == 5
        assert payload["baud"] == 115200


class TestAuthAndUartEdgeCases:
    def test_api_output_without_password_allows_anonymous(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("WEB_PASSWORD", raising=False)
        monkeypatch.delenv("CIRCUITPY_WEB_API_PASSWORD", raising=False)
        server, web, _, buf = make_terminal_server()
        buf.append(b"anon ok")
        response = web.api_output(build_request(server, "GET", "/api/output?since=0"))
        assert json_payload(response)["data"] == "anon ok"

    def test_password_falls_back_to_circuitpython_web_api_password(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("WEB_PASSWORD", raising=False)
        monkeypatch.setenv("CIRCUITPY_WEB_API_PASSWORD", "api-secret")
        assert _password() == "api-secret"

    def test_poll_uart_records_stats_and_survives_oserror(self) -> None:
        stats = UartStats()
        uart = FailingUart()
        server, web, _, buf = make_terminal_server(uart=uart, stats=stats)
        web._poll_uart()
        assert stats.read_errors == 1
        assert len(buf) == 0

    def test_api_status_includes_tx_and_read_errors(self, web_password: None) -> None:
        stats = UartStats()
        server, web, uart, _ = make_terminal_server(stats=stats)
        web.api_input(
            build_request(
                server,
                "POST",
                "/api/input",
                body=b"hi",
                extra_headers={"Cookie": AUTH_COOKIE},
            )
        )
        stats.record_read_error()
        response = web.api_status(
            build_request(
                server,
                "GET",
                "/api/status",
                extra_headers={"Cookie": AUTH_COOKIE},
            )
        )
        payload = json_payload(response)
        assert payload["tx_total"] == 2
        assert payload["read_errors"] == 1
        assert uart.written == [b"hi"]


class TestCreateServer:
    def test_create_server_binds_web_port(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("WEB_PORT", "9090")
        mock_server_cls = MagicMock()
        mock_instance = MagicMock()
        mock_server_cls.return_value = mock_instance
        with patch("adafruit_httpserver.Server", mock_server_cls):
            import socket

            create_server(socket, MagicMock(), UartBuffer())
        mock_instance.start.assert_called_once_with(host="0.0.0.0", port=9090)


class TestLogoutHandler:
    def test_logout_clears_session_and_writes_exit(
        self, terminal: tuple, web_password: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from esp_remote.firmware import session as sess

        monkeypatch.setenv("WEB_SESSION_TTL_S", "60")
        server, web, uart, _ = terminal
        sess.start_session()
        request = build_request(
            server,
            "POST",
            "/logout",
            extra_headers={
                "Cookie": AUTH_COOKIE,
                "Accept": "application/json",
            },
        )
        response = web.logout(request)
        assert json_payload(response) == {"ok": True}
        assert "Max-Age=0" in (response_header(response, "Set-Cookie") or "")
        assert uart.written == [b"\r\nexit\r\n"]
        assert sess.session_expired() is True

    def test_logout_without_cookie_skips_uart_still_clears_cookie(
        self, terminal: tuple, web_password: None
    ) -> None:
        server, web, uart, _ = terminal
        response = web.logout(
            build_request(
                server,
                "POST",
                "/logout",
                extra_headers={"Accept": "application/json"},
            )
        )
        assert json_payload(response) == {"ok": True}
        assert "Max-Age=0" in (response_header(response, "Set-Cookie") or "")
        assert uart.written == []


class TestLiveHttp:
    def test_post_login_over_tcp(self, web_password: None) -> None:
        server, _, _, _ = make_terminal_server()
        live = LiveServer(server)
        try:
            live.start()
            status, headers, body = live.request(
                "POST",
                "/login",
                body=_BROWSER_LOGIN_BODY.encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            assert status == 302
            assert headers.get("location") == "/terminal.html"
            assert AUTH_COOKIE in (headers.get("set-cookie") or "")
            assert body == b""
        finally:
            live.stop()

    def test_api_output_over_tcp_requires_cookie(self, web_password: None) -> None:
        server, _, _, buf = make_terminal_server()
        buf.append(b"hello")
        live = LiveServer(server)
        try:
            live.start()
            status, _, _ = live.request("GET", "/api/output?since=0")
            assert status == 401

            status, headers, body = live.request(
                "GET",
                "/api/output?since=0",
                headers={"Cookie": AUTH_COOKIE},
            )
            assert status == 200
            payload = json.loads(body.decode())
            assert payload["data"] == "hello"
            assert payload["since"] == 5
        finally:
            live.stop()

    def test_login_html_is_served(self, web_password: None) -> None:
        server, _, _, _ = make_terminal_server()
        live = LiveServer(server)
        try:
            live.start()
            status, headers, body = live.request("GET", "/login.html")
            assert status == 200
            assert "text/html" in (headers.get("content-type") or "")
            text = body.decode()
            assert 'action="/login"' in text
            assert 'method="post"' in text
            assert 'name="password"' in text
        finally:
            live.stop()
