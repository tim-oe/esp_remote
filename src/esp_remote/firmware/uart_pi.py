"""UART connection to the Raspberry Pi serial console."""

import os


def int_setting(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def bool_setting(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def open_pi_uart():
    """Open UART to the Pi (Feather TX → Pi RX, Feather RX ← Pi TX)."""
    import board  # noqa: PLC0415
    import busio  # noqa: PLC0415

    baud = int_setting("PI_UART_BAUD", 115200)
    # Larger RX buffer helps capture boot spew from the Pi.
    # Large hardware RX buffer helps survive reboot/kernel spew between poll ticks.
    rx_hw = int_setting("PI_UART_RX_BUFFER", 8192)
    uart = busio.UART(
        board.TX,
        board.RX,
        baudrate=baud,
        timeout=0,
        receiver_buffer_size=rx_hw,
    )
    print(f"uart: {baud} baud TX={board.TX} RX={board.RX}")
    return uart


def boot_banner(ip: str, port: int) -> bytes:
    """Startup line in the web UI to verify HTTP works without Pi serial."""
    if bool_setting("UART_BANNER", True):
        return (
            f"\r\n[esp_remote] bridge ready — http://{ip}:{port}/\r\n"
            "[esp_remote] If you only see this line, check Pi serial wiring "
            "and /boot/firmware config (enable_uart=1).\r\n"
        ).encode("utf-8")
    return b""
