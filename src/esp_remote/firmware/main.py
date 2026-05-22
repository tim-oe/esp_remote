"""Firmware entry: WiFi + UART to Pi + HTTP web terminal on ESP32."""

import time

_POLL_S = 0.01


def _drain_uart(uart, rx_buffer, stats) -> None:
    from esp_remote.firmware.uart_drain import (  # noqa: PLC0415
        DEFAULT_DRAIN_MAX_BYTES,
        drain_uart,
    )

    drain_uart(uart, rx_buffer, stats, max_bytes=DEFAULT_DRAIN_MAX_BYTES)


def main() -> None:
    import os  # noqa: PLC0415

    import socketpool  # noqa: PLC0415
    import wifi  # noqa: PLC0415

    from esp_remote.firmware.uart_buffer import UartBuffer  # noqa: PLC0415
    from esp_remote.firmware.uart_pi import (  # noqa: PLC0415
        boot_banner,
        int_setting,
        open_pi_uart,
    )
    from esp_remote.firmware.uart_stats import UartStats  # noqa: PLC0415
    from esp_remote.firmware.web_terminal import create_server  # noqa: PLC0415
    from esp_remote.firmware.wifi_setup import connect  # noqa: PLC0415

    ip = connect()
    port = int(os.getenv("WEB_PORT") or "8080")
    print(f"esp_remote: terminal http://{ip}:{port}/")

    pool = socketpool.SocketPool(wifi.radio)
    uart = open_pi_uart()
    rx_max = int_setting("UART_RX_MAX_BYTES", 16384)
    rx_buffer = UartBuffer(max_bytes=rx_max)
    stats = UartStats()
    banner = boot_banner(ip, port)
    if banner:
        rx_buffer.append(banner)

    server = create_server(pool, uart, rx_buffer, stats=stats)

    while True:
        server.poll()
        _drain_uart(uart, rx_buffer, stats)
        time.sleep(_POLL_S)
