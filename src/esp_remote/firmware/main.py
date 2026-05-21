"""Firmware entry: WiFi + UART to Pi + HTTP web terminal on ESP32."""

import time

_POLL_S = 0.01


def _drain_uart(uart, rx_buffer, stats) -> None:
    try:
        waiting = uart.in_waiting
        if waiting:
            chunk = uart.read(min(waiting, 256))
            if chunk:
                rx_buffer.append(chunk)
                stats.record_rx(len(chunk))
    except OSError:
        stats.record_read_error()


def main() -> None:
    import os  # noqa: PLC0415

    import socketpool  # noqa: PLC0415
    import wifi  # noqa: PLC0415

    from esp_remote.firmware.uart_buffer import UartBuffer  # noqa: PLC0415
    from esp_remote.firmware.uart_pi import boot_banner, open_pi_uart  # noqa: PLC0415
    from esp_remote.firmware.uart_stats import UartStats  # noqa: PLC0415
    from esp_remote.firmware.web_terminal import create_server  # noqa: PLC0415
    from esp_remote.firmware.wifi_setup import connect  # noqa: PLC0415

    ip = connect()
    port = int(os.getenv("WEB_PORT") or "8080")
    print(f"esp_remote: terminal http://{ip}:{port}/")

    pool = socketpool.SocketPool(wifi.radio)
    uart = open_pi_uart()
    rx_buffer = UartBuffer()
    stats = UartStats()
    banner = boot_banner(ip, port)
    if banner:
        rx_buffer.append(banner)

    server = create_server(pool, uart, rx_buffer, stats=stats)

    while True:
        server.poll()
        _drain_uart(uart, rx_buffer, stats)
        time.sleep(_POLL_S)
