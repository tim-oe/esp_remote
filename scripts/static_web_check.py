"""Validate static HTML/JS paths for ESP32 httpserver root_path serving.

With ``Server(pool, "/static")``, files live in ``CIRCUITPY/static/`` but URLs
are ``/login.html`` and ``/style.css`` — not ``/static/style.css``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "static"

# href="/foo" or src='/foo' — local absolute paths only
_LOCAL_PATH_RE = re.compile(
    r"""(?:href|src)\s*=\s*["'](\/[^"']+)["']""",
    re.IGNORECASE,
)

# Firmware must use positional root_path, not static_dir=
_SERVER_STATIC_DIR_RE = re.compile(r"Server\s*\([^)]*static_dir\s*=")


def collect_local_paths(html: str) -> list[str]:
    """Return root-relative paths (e.g. /style.css) from href/src attributes."""
    return [m.group(1) for m in _LOCAL_PATH_RE.finditer(html)]


def validate_static_files(
    static_dir: Path = STATIC_DIR,
    *,
    forbid_static_url_prefix: bool = True,
) -> list[str]:
    """Return human-readable validation errors (empty if OK)."""
    errors: list[str] = []
    if not static_dir.is_dir():
        return [f"static directory missing: {static_dir}"]

    for html_path in sorted(static_dir.glob("*.html")):
        text = html_path.read_text(encoding="utf-8")
        for url_path in collect_local_paths(text):
            if forbid_static_url_prefix and url_path.startswith("/static/"):
                errors.append(
                    f"{html_path.name}: {url_path} — use {url_path[len('/static'):]} "
                    f"(httpserver root_path is /static on device)"
                )
                continue
            rel = url_path.lstrip("/")
            target = static_dir / rel
            if not target.is_file():
                errors.append(f"{html_path.name}: {url_path} — no file {target}")

    return errors


def validate_firmware_httpserver(static_dir: Path = STATIC_DIR) -> list[str]:
    """Check firmware uses correct adafruit_httpserver Server() API."""
    errors: list[str] = []
    firmware = REPO_ROOT / "src" / "esp_remote" / "firmware"
    web_terminal = firmware / "web_terminal.py"
    if not web_terminal.is_file():
        return errors

    text = web_terminal.read_text(encoding="utf-8")
    if _SERVER_STATIC_DIR_RE.search(text):
        errors.append(
            "web_terminal.py: use Server(pool, \"/static\") not static_dir= "
            "(CircuitPython adafruit_httpserver API)"
        )
    if "static_dir=" in text:
        errors.append("web_terminal.py: unexpected static_dir= keyword")
    if re.search(r"status=\d+\b", text):
        errors.append(
            "web_terminal.py: use status=(code, 'text') or Redirect(), not status=302"
        )

    return errors


def run_all_checks() -> list[str]:
    return validate_static_files() + validate_firmware_httpserver()


def main() -> int:
    errors = run_all_checks()
    if errors:
        print("Static web validation failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Static web validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
