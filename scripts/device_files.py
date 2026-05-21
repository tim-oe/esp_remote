"""Paths deployed to the CircuitPython device."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_NAME = "esp_remote"
LIB_SRC = REPO_ROOT / "src" / PACKAGE_NAME
STATIC_DIR = REPO_ROOT / "static"


def device_library_files() -> list[Path]:
    """Python files copied to CIRCUITPY/lib/esp_remote/."""
    files: list[Path] = []
    init_py = LIB_SRC / "__init__.py"
    if init_py.is_file():
        files.append(init_py)
    firmware = LIB_SRC / "firmware"
    if firmware.is_dir():
        files.extend(sorted(firmware.rglob("*.py")))
    return files


def device_static_files() -> list[Path]:
    """Static web assets copied to CIRCUITPY/static/."""
    if not STATIC_DIR.is_dir():
        return []
    return sorted(
        p for p in STATIC_DIR.rglob("*") if p.is_file() and not p.name.startswith(".")
    )
