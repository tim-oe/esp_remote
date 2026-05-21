"""HTTP helpers for CircuitPython Web Workflow (port 80, /fs/ API)."""

from __future__ import annotations

import base64
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path

_DEFAULT_CONNECT_S = 15
_DEFAULT_READ_S = 120
_MAX_RETRIES = 3
_RETRY_DELAY_S = 2.0


def auth_header(password: str) -> dict[str, str]:
    token = base64.b64encode(f":{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _merge_headers(extra: dict[str, str], auth: dict[str, str]) -> dict[str, str]:
    merged = dict(auth)
    merged.update(extra)
    return merged


def check_workflow(
    host: str,
    password: str,
    port: int = 80,
    *,
    connect_timeout: float = _DEFAULT_CONNECT_S,
) -> None:
    """Verify Web Workflow responds before a long deploy."""
    url = f"http://{host}:{port}/fs/"
    auth = auth_header(password)
    req = urllib.request.Request(
        url,
        method="PUT",
        data=b"",
        headers=_merge_headers({"Content-Type": "application/octet-stream"}, auth),
    )
    try:
        with urllib.request.urlopen(req, timeout=connect_timeout):
            pass
    except urllib.error.HTTPError as exc:
        if exc.code in (200, 201, 204):
            return
        raise RuntimeError(f"Web Workflow at {url} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Cannot reach CircuitPython Web Workflow at {host}:{port}.\n"
            "  - Confirm ESP32_IP in settings.toml matches the REPL address.\n"
            "  - Web Workflow uses port 80 (separate from WEB_PORT=8080 terminal).\n"
            "  - If code.py crashed, fix via USB: poetry run deploy --serial --settings\n"
            "  - Ensure settings.toml on the device has CIRCUITPY_WEB_API_PASSWORD set."
        ) from exc


def put_bytes(
    host: str,
    remote_path: str,
    data: bytes,
    auth: dict[str, str],
    *,
    port: int = 80,
    connect_timeout: float = _DEFAULT_CONNECT_S,
    read_timeout: float = _DEFAULT_READ_S,
) -> None:
    url = f"http://{host}:{port}/fs/{remote_path}"
    headers = _merge_headers({"Content-Type": "application/octet-stream"}, auth)
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    timeout = connect_timeout + read_timeout
    last_err: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
            if status in (200, 201, 204):
                return
            raise RuntimeError(f"PUT {url} failed with HTTP {status}")
        except urllib.error.HTTPError as exc:
            if exc.code in (200, 201, 204):
                return
            raise RuntimeError(f"PUT {url} failed with HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_err = exc
            if attempt < _MAX_RETRIES:
                print(f"  [retry {attempt}/{_MAX_RETRIES}] {remote_path}: {exc}")
                time.sleep(_RETRY_DELAY_S)
            continue
    raise RuntimeError(f"PUT {url} timed out after {_MAX_RETRIES} attempts") from last_err


def put_file(
    host: str,
    remote_path: str,
    local_path: Path,
    auth: dict[str, str],
    *,
    port: int = 80,
) -> None:
    put_bytes(host, remote_path, local_path.read_bytes(), auth, port=port)


def mkdir_remote(
    host: str,
    remote_dir: str,
    auth: dict[str, str],
    *,
    port: int = 80,
) -> None:
    put_bytes(host, f"{remote_dir.strip('/')}/", b"", auth, port=port)
