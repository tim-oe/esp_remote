"""Tests for UART byte counters."""

from esp_remote.firmware.uart_stats import UartStats


def test_record_rx_tx_and_errors() -> None:
    stats = UartStats()
    stats.record_rx(10)
    stats.record_rx(5)
    stats.record_tx(3)
    stats.record_read_error()
    assert stats.rx_bytes == 15
    assert stats.tx_bytes == 3
    assert stats.read_errors == 1
