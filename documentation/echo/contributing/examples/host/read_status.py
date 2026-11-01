"""Read-only USB CLI example. Run with --help; requires pyserial."""

import argparse
import sys
import time

import serial
from serial.tools import list_ports

COMMANDS = ("device_info", "loader info", "free")


def read_window(connection, duration):
    """Keep reading for a fixed window, including through quiet intervals."""
    deadline = time.monotonic() + duration
    chunks = []
    while time.monotonic() < deadline:
        chunks.append(connection.read(max(1, connection.in_waiting)))
    return b"".join(chunks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port", help="Explicit serial device; otherwise discover one Flipper"
    )
    parser.add_argument("--command", choices=COMMANDS, default="loader info")
    parser.add_argument(
        "--seconds", type=float, default=5, help="Fixed reply window (1–60)"
    )
    args = parser.parse_args()
    if not 1 <= args.seconds <= 60:
        parser.error("--seconds must be between 1 and 60")
    port = args.port
    if not port:
        candidates = [
            p.device for p in list_ports.comports() if "flip" in p.device.lower()
        ]
        if len(candidates) != 1:
            parser.error(
                "Expected one Flipper; specify --port after inspecting serial ports"
            )
        port = candidates[0]
    # USB CDC baud is distinct from the ESP32's GPIO UART baud.
    with serial.Serial(port, 115200, timeout=0.1, write_timeout=2) as connection:
        connection.write(b"\r")
        read_window(connection, 0.3)
        connection.write((args.command + "\r").encode("ascii"))
        reply = read_window(connection, args.seconds)
    sys.stdout.write(reply.decode("utf-8", errors="replace"))
    if not reply.strip():
        print(
            "No reply; this does not prove completion or disconnection", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
