"""Capture ESP32 sender logs without resetting or reconfiguring the board."""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import serial


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture ESP32 sender serial logs for a bounded diagnostic interval.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--duration-s", type=float, default=65.0)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--reset", action="store_true", help="Issue a normal reset after opening the serial port.")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.duration_s
    # Read raw chunks instead of readline()+flush per record.  The sender can
    # emit hundreds of thousands of CSV rows after a run; line-at-a-time I/O
    # can make the host fall behind even when the serial link is fast enough.
    with serial.Serial(args.port, args.baud, timeout=0.1) as device, args.out.open("wb") as output:
        # Keep GPIO0 released while pulsing EN through the standard USB-UART reset circuit.
        device.dtr = False
        device.rts = False
        if args.reset:
            device.rts = True
            time.sleep(0.12)
            device.rts = False
            time.sleep(0.25)
        header = f"# started_at={datetime.now().isoformat(timespec='seconds')} port={args.port} baud={args.baud}\n".encode()
        output.write(header)
        while time.monotonic() < deadline:
            waiting = device.in_waiting
            chunk = device.read(max(waiting, 1))
            if not chunk:
                continue
            output.write(chunk)
            output.flush()


if __name__ == "__main__":
    main()
