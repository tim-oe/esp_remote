"""Verify ESP32 web terminal HTTP + UART path from your dev machine.

Exercises the same APIs the browser uses: login, status, output poll, and
sends Enter to wake the Pi serial console.

Usage:
    poetry run verify-terminal
    poetry run verify-terminal --send "help\r\n"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = REPO_ROOT / "settings.toml"


def load_settings() -> tuple[str, int, str]:
    if not SETTINGS_PATH.is_file():
        print(f"Error: {SETTINGS_PATH} not found", file=sys.stderr)
        sys.exit(1)
    with open(SETTINGS_PATH, "rb") as handle:
        data = tomllib.load(handle)
    host = str(data.get("ESP32_IP", "")).strip()
    if not host:
        print("Error: ESP32_IP missing in settings.toml", file=sys.stderr)
        sys.exit(1)
    port = int(data.get("WEB_PORT") or 8080)
    password = str(data.get("WEB_PASSWORD", "")).strip()
    if not password:
        password = str(data.get("CIRCUITPY_WEB_API_PASSWORD", "")).strip()
    if not password:
        print("Error: WEB_PASSWORD missing in settings.toml", file=sys.stderr)
        sys.exit(1)
    return host, port, password


class TerminalClient:
    def __init__(self, base_url: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.password = password
        self._jar = CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar)
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        url = self.base_url + path
        req = urllib.request.Request(url, data=data, method=method)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with self._opener.open(req, timeout=8) as resp:
                body = resp.read()
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, hdrs, body
        except urllib.error.HTTPError as exc:
            body = exc.read()
            hdrs = {k.lower(): v for k, v in exc.headers.items()}
            return exc.code, hdrs, body

    def _has_auth_cookie(self) -> bool:
        for cookie in self._jar:
            if cookie.name == "esp_auth" and cookie.value == "1":
                return True
        return False

    def login(self) -> None:
        form = urllib.parse.urlencode({"password": self.password}).encode()
        status, headers, _ = self._request(
            "POST",
            "/login",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status == 401:
            raise RuntimeError("login failed: invalid password (HTTP 401)")
        # urllib follows 302 → /terminal.html, so final status is often 200.
        if self._has_auth_cookie():
            return
        cookie = headers.get("set-cookie", "")
        if "esp_auth=1" in cookie:
            return
        raise RuntimeError(
            f"login failed: HTTP {status}, no esp_auth session cookie"
        )

    def status(self) -> dict:
        status, _, body = self._request("GET", "/api/status")
        if status != 200:
            raise RuntimeError(f"/api/status HTTP {status}: {body[:200]!r}")
        return json.loads(body.decode())

    def output(self, since: int = 0) -> dict:
        status, _, body = self._request("GET", f"/api/output?since={since}")
        if status != 200:
            raise RuntimeError(f"/api/output HTTP {status}: {body[:200]!r}")
        return json.loads(body.decode())

    def input_bytes(self, payload: bytes) -> dict:
        status, _, body = self._request("POST", "/api/input", data=payload)
        if status != 200:
            raise RuntimeError(f"/api/input HTTP {status}: {body[:200]!r}")
        return json.loads(body.decode())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--send",
        default="\r\n",
        help="Bytes to send to Pi serial after login (default: Enter)",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=1.5,
        help="Seconds to wait for Pi/bridge output after sending",
    )
    args = parser.parse_args()

    host, port, password = load_settings()
    base = f"http://{host}:{port}"
    client = TerminalClient(base, password)

    print(f"Target: {base}")
    print("1. Logging in …")
    client.login()
    print("   OK (session cookie set)")

    print("2. Reading /api/status …")
    st0 = client.status()
    print(
        f"   rx_total={st0['rx_total']} buffer_bytes={st0['buffer_bytes']} "
        f"baud={st0['baud']}"
    )

    print("3. Polling /api/output …")
    out0 = client.output(0)
    banner = out0.get("data", "")
    if banner:
        print("   Bridge banner (HTTP path OK):")
        for line in banner.splitlines():
            print(f"     | {line}")
    else:
        print("   WARNING: no output yet — deploy latest firmware (UART_BANNER)")

    payload = args.send.encode("utf-8")
    print(f"4. Sending {len(payload)} byte(s) to Pi via /api/input …")
    sent = client.input_bytes(payload)
    print(f"   OK bytes={sent.get('bytes', len(payload))}")

    time.sleep(args.wait)

    print("5. Polling /api/output again …")
    out1 = client.output(out0.get("since", 0))
    new_data = out1.get("data", "")
    st1 = client.status()

    if new_data:
        print("   New serial data:")
        for line in new_data.splitlines():
            print(f"     | {line}")
    else:
        print("   No new bytes after send.")

    print(
        f"6. Summary: rx_total {st0['rx_total']} -> {st1['rx_total']}, "
        f"tx_total={st1['tx_total']}, uart_pending={st1['uart_pending']}"
    )

    ok_http = bool(banner) or st0["rx_total"] > 0
    ok_pi = st1["rx_total"] > st0["rx_total"] or bool(new_data)

    if ok_http and ok_pi:
        print("\nPASS: HTTP terminal works and Pi serial is responding.")
        return 0
    if ok_http and not ok_pi:
        print(
            "\nPARTIAL: Browser/HTTP bridge works, but Pi is not sending serial data.",
            file=sys.stderr,
        )
        print(
            "  Check: Pi powered, GPIO14/15 wiring (TX↔RX crossed), GND common,",
            file=sys.stderr,
        )
        print(
            "  enable_uart=1, console=serial0 in /boot/firmware/config.txt,",
            file=sys.stderr,
        )
        print("  115200 baud.", file=sys.stderr)
        return 2
    print(
        "\nFAIL: No data from ESP32 — redeploy firmware and confirm ESP32_IP.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
