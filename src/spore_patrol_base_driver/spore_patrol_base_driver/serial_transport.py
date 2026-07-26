"""Dependency-free nonblocking Linux serial transport."""

import os
import select
import termios
from typing import Optional


BAUD_CONSTANTS = {
    9600: termios.B9600,
    19200: termios.B19200,
    38400: termios.B38400,
    57600: termios.B57600,
    115200: termios.B115200,
    230400: termios.B230400,
}


class LinuxSerialPort:
    """Small termios serial wrapper suitable for a ROS timer callback."""

    def __init__(self, device: str, baud: int) -> None:
        if baud not in BAUD_CONSTANTS:
            raise ValueError(f"unsupported baud rate: {baud}")
        self.device = device
        self.baud = baud
        self.fd: Optional[int] = None

    @property
    def is_open(self) -> bool:
        return self.fd is not None

    def open(self) -> None:
        if self.fd is not None:
            return
        fd = os.open(
            self.device,
            os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK,
        )
        try:
            attrs = termios.tcgetattr(fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
            attrs[3] = 0
            attrs[4] = BAUD_CONSTANTS[self.baud]
            attrs[5] = BAUD_CONSTANTS[self.baud]
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            termios.tcflush(fd, termios.TCIOFLUSH)
        except Exception:
            os.close(fd)
            raise
        self.fd = fd

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def read(self, size: int = 4096) -> bytes:
        if self.fd is None:
            raise RuntimeError("serial port is not open")
        try:
            return os.read(self.fd, size)
        except BlockingIOError:
            return b""

    def write(self, data: bytes, timeout: float = 0.05) -> None:
        if self.fd is None:
            raise RuntimeError("serial port is not open")
        view = memoryview(data)
        while view:
            _, writable, _ = select.select([], [self.fd], [], timeout)
            if not writable:
                raise TimeoutError("serial write timed out")
            written = os.write(self.fd, view)
            view = view[written:]
