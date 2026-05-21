"""CircuitPython compatibility checks for device firmware.

Host pytest uses CPython 3.13, which accepts syntax MicroPython on the ESP32
does not (e.g. dict unpacking ``{**d}``). These tests scan firmware sources
for known-incompatible patterns so deploy-time SyntaxErrors are caught in CI.
"""

import re
from pathlib import Path

FIRMWARE_DIR = Path(__file__).resolve().parents[1] / "src" / "esp_remote" / "firmware"

# (regex, human-readable reason)
_FORBIDDEN: list[tuple[str, str]] = [
    (r"\{[^}]*\*\*[^}]*\}", "dict unpacking {**...} is not valid on CircuitPython"),
    (r"static_dir\s*=", "adafruit_httpserver uses Server(pool, root_path) positional"),
    (
        r"status=\d+\b",
        "httpserver status must be (code, 'text') tuple or use Redirect",
    ),
    (
        r"""split\(\s*["']password=["']""",
        "login must use parse_form_urlencoded (see form_parse.py)",
    ),
    (
        r"\.decode\([^)]*errors\s*=",
        "use bytes_to_text() — CircuitPython decode() has no errors= kwarg",
    ),
    (r"\bmatch\b\s+", "match/case may be unsupported on older CircuitPython builds"),
    (r"\bcase\b\s+", "match/case may be unsupported on older CircuitPython builds"),
]


def test_firmware_avoids_cpython_only_syntax() -> None:
    violations: list[str] = []
    for path in sorted(FIRMWARE_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            for pattern, reason in _FORBIDDEN:
                if re.search(pattern, line):
                    rel = path.relative_to(FIRMWARE_DIR)
                    snippet = line.strip()
                    violations.append(f"{rel}:{line_no}: {reason}\n  {snippet}")
    assert not violations, "CircuitPython-incompatible syntax:\n" + "\n".join(
        violations
    )
