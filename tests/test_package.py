"""Smoke tests for the esp_remote package."""

from unittest.mock import patch

import esp_remote


def test_version() -> None:
    assert esp_remote.__version__ == "0.1.0"


def test_run_starts_firmware() -> None:
    with patch("esp_remote.firmware.main.main") as firmware_main:
        esp_remote.run()
    firmware_main.assert_called_once()
