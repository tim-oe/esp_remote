"""Tests for firmware main-loop UART drain (no WiFi/hardware)."""

from unittest.mock import MagicMock, PropertyMock

from esp_remote.firmware.main import _drain_uart
from esp_remote.firmware.uart_buffer import UartBuffer
from esp_remote.firmware.uart_stats import UartStats


def test_drain_uart_appends_and_records_stats() -> None:
    uart = MagicMock()
    uart.in_waiting = 4
    uart.read.return_value = b"abcd"
    buf = UartBuffer()
    stats = UartStats()
    _drain_uart(uart, buf, stats)
    chunk, _, _ = buf.read_since(0)
    assert chunk == b"abcd"
    assert stats.rx_bytes == 4


def test_drain_uart_ignores_oserror() -> None:
    uart = MagicMock()
    type(uart).in_waiting = PropertyMock(side_effect=OSError("uart"))
    buf = UartBuffer()
    stats = UartStats()
    _drain_uart(uart, buf, stats)
    assert len(buf) == 0
    assert stats.read_errors == 1
