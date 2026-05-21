"""Counters shared by the main loop and HTTP handlers."""


class UartStats:
    def __init__(self) -> None:
        self.rx_bytes = 0
        self.tx_bytes = 0
        self.read_errors = 0

    def record_rx(self, nbytes: int) -> None:
        self.rx_bytes += nbytes

    def record_tx(self, nbytes: int) -> None:
        self.tx_bytes += nbytes

    def record_read_error(self) -> None:
        self.read_errors += 1
