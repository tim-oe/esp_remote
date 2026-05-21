"""Connect the ESP32 to WiFi using settings.toml credentials."""


def connect() -> str:
    """Join the configured network and return the IPv4 address as a string."""
    import os  # noqa: PLC0415

    import wifi  # noqa: PLC0415

    ssid = os.getenv("CIRCUITPY_WIFI_SSID", "")
    password = os.getenv("CIRCUITPY_WIFI_PASSWORD", "")
    if not ssid:
        raise RuntimeError("CIRCUITPY_WIFI_SSID is not set in settings.toml")

    print(f"wifi: connecting to {ssid} …")
    wifi.radio.connect(ssid, password)
    address = wifi.radio.ipv4_address
    if address is None:
        raise RuntimeError("wifi: connected but no IPv4 address")
    print(f"wifi: {address}")
    return str(address)
