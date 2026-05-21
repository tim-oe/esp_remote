"""Shared pytest configuration — stub CircuitPython modules for host tests."""

import sys
from unittest.mock import MagicMock

_STUB_NAMES = [
    "board",
    "busio",
    "digitalio",
    "wifi",
    "socketpool",
    "supervisor",
    "microcontroller",
]

for _name in _STUB_NAMES:
    if _name not in sys.modules:
        sys.modules[_name] = MagicMock()
