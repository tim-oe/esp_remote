"""Tests for CircuitPython dependency resolution."""

from pathlib import Path

from scripts.circuitpython_deps import (
    declared_pypi_packages,
    firmware_missing_bundle_modules,
    resolve_bundle_modules,
)
from scripts.device_files import device_library_files

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"
FIRMWARE = REPO / "src" / "esp_remote" / "firmware"


def test_httpserver_declared() -> None:
    assert "adafruit-circuitpython-httpserver" in declared_pypi_packages(PYPROJECT)
    assert "adafruit_httpserver" in resolve_bundle_modules(PYPROJECT)


def test_firmware_bundle_check_ok() -> None:
    assert firmware_missing_bundle_modules(PYPROJECT, FIRMWARE) == []


def test_device_library_excludes_removed_web() -> None:
    paths = [str(p) for p in device_library_files()]
    assert any("firmware/web_terminal.py" in p for p in paths)
    assert not any("/web/" in p for p in paths)
