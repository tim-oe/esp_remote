"""Tests for bounded UART drain into the capture buffer."""

from unittest.mock import MagicMock

from esp_remote.firmware.uart_buffer import UartBuffer
from esp_remote.firmware.uart_drain import drain_uart
from esp_remote.firmware.uart_stats import UartStats


class _FakeUart:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.read_sizes: list[int] = []

    @property
    def in_waiting(self) -> int:
        if not self._chunks:
            return 0
        return len(self._chunks[0])

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        if not self._chunks:
            return b""
        head = self._chunks[0]
        if len(head) <= size:
            self._chunks.pop(0)
            return head
        self._chunks[0] = head[size:]
        return head[:size]


def test_drain_uart_reads_until_empty_or_cap() -> None:
    uart = _FakeUart([b"a" * 300, b"b" * 300, b"c" * 100])
    buf = UartBuffer()
    stats = UartStats()
    drained = drain_uart(uart, buf, stats, max_bytes=500, chunk_size=256)
    assert drained == 500
    assert len(buf) == 500
    assert stats.rx_bytes == 500


def test_drain_uart_survives_oserror() -> None:
    uart = MagicMock()
    uart.in_waiting = 10
    uart.read.side_effect = OSError("uart down")
    buf = UartBuffer()
    stats = UartStats()
    assert drain_uart(uart, buf, stats) == 0
    assert stats.read_errors == 1
