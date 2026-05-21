"""Tests for the host-side terminal verification client."""

from __future__ import annotations

import json
from http.cookiejar import Cookie
from unittest.mock import patch

from scripts.verify_terminal import TerminalClient

_STATUS_JSON = {
    "rx_total": 120,
    "buffer_bytes": 10,
    "baud": 115200,
    "tx_total": 0,
    "uart_pending": 0,
    "read_errors": 0,
}


def test_terminal_client_login_and_poll_sequence() -> None:
    calls: list[tuple[str, str]] = []

    def fake_request(self, method, path, data=None, headers=None):
        calls.append((method, path))
        if method == "POST" and path == "/login":
            return 302, {"set-cookie": "esp_auth=1; Path=/"}, b""
        if path == "/api/status":
            return 200, {}, json.dumps(_STATUS_JSON).encode()
        if path.startswith("/api/output"):
            if "since=0" in path or path == "/api/output?since=0":
                payload = {"data": "[esp_remote] bridge ready\n", "since": 40}
                return 200, {}, json.dumps(payload).encode()
            return 200, {}, json.dumps({"data": "pi login:", "since": 49}).encode()
        if path == "/api/input":
            return 200, {}, json.dumps({"ok": True, "bytes": 2}).encode()
        return 404, {}, b""

    client = TerminalClient("http://192.168.1.25:8080", "test@pwd")
    with patch.object(TerminalClient, "_request", fake_request):
        client.login()
        st = client.status()
        out0 = client.output(0)
        client.input_bytes(b"\r\n")
        out1 = client.output(out0["since"])

    assert st["rx_total"] == 120
    assert "bridge ready" in out0["data"]
    assert out1["data"] == "pi login:"
    assert ("POST", "/login") in calls
    assert any(c[1].startswith("/api/output") for c in calls)


def test_login_accepts_200_when_session_cookie_in_jar() -> None:
    """urllib follows 302 to terminal.html — final response is HTTP 200."""

    def fake_request(self, method, path, data=None, headers=None):
        if method == "POST" and path == "/login":
            return 200, {}, b"<html>terminal</html>"
        return 404, {}, b""

    client = TerminalClient("http://192.168.1.25:8080", "test@pwd")
    client._jar.set_cookie(
        Cookie(
            version=0,
            name="esp_auth",
            value="1",
            port=None,
            port_specified=False,
            domain="192.168.1.25",
            domain_specified=True,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=False,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )
    )
    with patch.object(TerminalClient, "_request", fake_request):
        client.login()
