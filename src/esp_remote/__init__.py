"""esp_remote — ESP32 web terminal to Raspberry Pi serial over UART."""

__version__ = "0.1.0"


def run() -> None:
    """Start ESP32 firmware: WiFi + UART/TCP bridge to the Pi."""
    from esp_remote.firmware.main import main as firmware_main

    firmware_main()
