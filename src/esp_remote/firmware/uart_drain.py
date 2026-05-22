"""Read bytes from the Pi UART into the HTTP capture buffer (bounded per call)."""

_UART_CHUNK = 256
# Keep HTTP handlers responsive; main loop uses the same cap per tick.
DEFAULT_DRAIN_MAX_BYTES = 2048


def drain_uart(
    uart,
    rx_buffer,
    stats=None,
    *,
    max_bytes: int = DEFAULT_DRAIN_MAX_BYTES,
    chunk_size: int = _UART_CHUNK,
) -> int:
    """Drain up to *max_bytes* from UART into *rx_buffer*. Returns bytes read."""
    drained = 0
    while drained < max_bytes:
        try:
            waiting = int(uart.in_waiting or 0)
        except OSError as exc:
            print(f"uart in_waiting: {exc}")
            if stats is not None:
                stats.record_read_error()
            break
        if waiting <= 0:
            break
        to_read = min(waiting, chunk_size, max_bytes - drained)
        try:
            chunk = uart.read(to_read)
        except OSError as exc:
            print(f"uart read: {exc}")
            if stats is not None:
                stats.record_read_error()
            break
        if not chunk:
            break
        rx_buffer.append(chunk)
        if stats is not None:
            stats.record_rx(len(chunk))
        drained += len(chunk)
    return drained
