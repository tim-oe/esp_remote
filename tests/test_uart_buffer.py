"""Tests for UART capture buffer (host-side)."""

from esp_remote.firmware.uart_buffer import GAP_NOTICE, UartBuffer


def test_append_empty_chunk_is_noop() -> None:
    buf = UartBuffer()
    buf.append(b"")
    assert len(buf) == 0
    assert buf.total_rx == 0


def test_read_since_negative_cursor_treated_as_zero() -> None:
    buf = UartBuffer()
    buf.append(b"ab")
    chunk, cursor, gap = buf.read_since(-1)
    assert chunk == b"ab"
    assert cursor == 2
    assert gap is False


def test_append_and_read_stream_cursor() -> None:
    buf = UartBuffer(max_bytes=100, poll_chunk=512)
    buf.append(b"abc")
    chunk, cursor, gap = buf.read_since(0)
    assert chunk == b"abc"
    assert cursor == 3
    assert gap is False

    more, cursor2, gap2 = buf.read_since(cursor)
    assert more == b""
    assert cursor2 == 3
    assert gap2 is False

    buf.append(b"def")
    more, cursor3, gap3 = buf.read_since(3)
    assert more == b"def"
    assert cursor3 == 6
    assert gap3 is False


def test_trims_when_full() -> None:
    buf = UartBuffer(max_bytes=4, poll_chunk=512)
    buf.append(b"123456")
    assert len(buf) == 4
    assert buf.stream_base() == 2
    chunk, cursor, gap = buf.read_since(2)
    assert chunk == b"3456"
    assert cursor == 6
    assert gap is False
    _, cursor0, gap0 = buf.read_since(0)
    assert gap0 is True
    assert cursor0 == 6


def test_total_rx_counts_all_appended_bytes() -> None:
    buf = UartBuffer(max_bytes=4, poll_chunk=512)
    buf.append(b"123456")
    assert buf.total_rx == 6
    assert len(buf) == 4


def test_read_since_returns_partial_chunks() -> None:
    buf = UartBuffer(max_bytes=100, poll_chunk=4)
    buf.append(b"abcdefgh")
    first, c1, _ = buf.read_since(0)
    assert first == b"abcd"
    assert c1 == 4
    second, c2, _ = buf.read_since(c1)
    assert second == b"efgh"
    assert c2 == 8


def test_read_since_after_trim_uses_stream_position() -> None:
    """Regression: buffer index cursor broke during apt-sized output bursts."""
    buf = UartBuffer(max_bytes=10, poll_chunk=100)
    buf.append(b"0123456789")
    _, c1, _ = buf.read_since(0)
    assert c1 == 10
    buf.append(b"abcdefghij")
    assert buf.stream_base() == 10
    chunk, c2, gap = buf.read_since(10)
    assert chunk == b"abcdefghij"
    assert c2 == 20
    assert gap is False


def test_read_since_detects_gap_after_trim() -> None:
    buf = UartBuffer(max_bytes=10, poll_chunk=100)
    buf.append(b"0123456789")
    buf.append(b"abcdefghij")
    chunk, cursor, gap = buf.read_since(2)
    assert gap is True
    assert chunk == b"abcdefghij"
    assert cursor == 20


def test_gap_notice_constant_present() -> None:
    assert b"dropped from buffer" in GAP_NOTICE
