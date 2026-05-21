"""Tests for UART settings helpers (no hardware)."""

from esp_remote.firmware.uart_pi import bool_setting, boot_banner, int_setting


def test_int_setting_default_and_override(monkeypatch) -> None:
    monkeypatch.delenv("PI_UART_BAUD", raising=False)
    assert int_setting("PI_UART_BAUD", 115200) == 115200
    monkeypatch.setenv("PI_UART_BAUD", "9600")
    assert int_setting("PI_UART_BAUD", 115200) == 9600
    monkeypatch.setenv("PI_UART_BAUD", "")
    assert int_setting("PI_UART_BAUD", 115200) == 115200


def test_bool_setting_truthy_values(monkeypatch) -> None:
    for value in ("1", "true", "YES", "on"):
        monkeypatch.setenv("UART_BANNER", value)
        assert bool_setting("UART_BANNER", False) is True
    monkeypatch.setenv("UART_BANNER", "0")
    assert bool_setting("UART_BANNER", True) is False
    monkeypatch.delenv("UART_BANNER", raising=False)
    assert bool_setting("UART_BANNER", True) is True


def test_boot_banner_enabled_and_disabled(monkeypatch) -> None:
    monkeypatch.delenv("UART_BANNER", raising=False)
    text = boot_banner("10.0.0.5", 8080).decode()
    assert "bridge ready" in text
    assert "10.0.0.5:8080" in text
    monkeypatch.setenv("UART_BANNER", "0")
    assert boot_banner("10.0.0.5", 8080) == b""
