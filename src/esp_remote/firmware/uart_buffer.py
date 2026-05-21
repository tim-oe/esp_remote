"""Fixed-size RX capture for UART → HTTP terminal polling."""

# Cap each /api/output response so the ESP32 is not stuck sending huge JSON.
DEFAULT_POLL_CHUNK = 512

# Shown once when the client cursor points at data already trimmed from the buffer.
GAP_NOTICE = b"\r\n[esp_remote: earlier output dropped from buffer]\r\n"


class UartBuffer:
    """Append-only byte buffer with stream-position reads for poll clients."""

    def __init__(
        self, max_bytes: int = 8192, poll_chunk: int = DEFAULT_POLL_CHUNK
    ) -> None:
        self._max = max_bytes
        self._poll_chunk = poll_chunk
        self._data = bytearray()
        self._total_rx = 0

    @property
    def total_rx(self) -> int:
        """Total bytes ever received from UART (including trimmed data)."""
        return self._total_rx

    def stream_base(self) -> int:
        """Stream offset of the first byte still held in the ring buffer."""
        return self._total_rx - len(self._data)

    def append(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._total_rx += len(chunk)
        self._data.extend(chunk)
        if len(self._data) > self._max:
            self._data = self._data[-self._max :]

    def read_since(self, stream_cursor: int) -> tuple[bytes, int, bool]:
        """Read up to ``poll_chunk`` bytes from the UART stream.

        *stream_cursor* is the total number of UART bytes the client has already
        consumed (``since`` from the previous poll), not an index into the buffer.

        Returns ``(chunk, new_stream_cursor, gap)`` where *gap* is true when
        *stream_cursor* pointed at trimmed data.
        """
        if stream_cursor < 0:
            stream_cursor = 0
        base = self.stream_base()
        gap = stream_cursor < base
        if gap:
            start = 0
        else:
            start = stream_cursor - base
        if start >= len(self._data):
            return b"", self._total_rx, gap
        end = start + self._poll_chunk
        if end > len(self._data):
            end = len(self._data)
        chunk = bytes(self._data[start:end])
        return chunk, base + end, gap

    def __len__(self) -> int:
        return len(self._data)
