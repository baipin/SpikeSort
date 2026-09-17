"""List Windows serial ports for the LAN field terminal."""

from __future__ import annotations

import json
import re
import subprocess
import sys


def port_label(description: str) -> str:
    """Use ASCII UI labels; Windows device names can use a legacy code page."""
    text = description.lower()
    if any(token in text for token in ("usb", "jtag", "cp210", "ch340", "ftdi", "uart")):
        return "USB serial device"
    if "bluetooth" in text or "bth" in text:
        return "Bluetooth serial port"
    return "Serial device"


def list_ports() -> list[dict[str, str]]:
    ports: dict[str, str] = {}
    try:
        import serial.tools.list_ports  # type: ignore
        for item in serial.tools.list_ports.comports():
            ports[item.device.upper()] = item.description or item.device
    except ImportError:
        pass
    if sys.platform == "win32":
        command = ["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_PnPEntity | Select-Object -ExpandProperty Name"]
        try:
            output = subprocess.check_output(command, text=True, encoding="utf-8", errors="replace",
                                             stderr=subprocess.DEVNULL)
            for line in output.splitlines():
                match = re.search(r"\((COM\d+)\)", line, re.IGNORECASE)
                if match:
                    ports.setdefault(match.group(1).upper(), line.strip())
        except (OSError, subprocess.CalledProcessError):
            pass
        # This registry map remains readable when CIM/PnP queries are blocked
        # by a managed Windows policy. It contains only ASCII device paths.
        registry_command = [
            "powershell", "-NoProfile", "-Command",
            "Get-ItemProperty 'HKLM:\\HARDWARE\\DEVICEMAP\\SERIALCOMM' | "
            "ForEach-Object { $_.PSObject.Properties | Where-Object { $_.Name -notmatch '^PS' } | "
            "ForEach-Object { $_.Name + '|' + $_.Value } }",
        ]
        try:
            output = subprocess.check_output(registry_command, text=True, encoding="utf-8",
                                             errors="replace", stderr=subprocess.DEVNULL)
            for line in output.splitlines():
                description, _, port = line.rpartition("|")
                if re.fullmatch(r"COM\d+", port.strip(), re.IGNORECASE):
                    ports.setdefault(port.strip().upper(), description.strip())
        except (OSError, subprocess.CalledProcessError):
            pass
    return [{"port": port, "label": port_label(ports[port])}
            for port in sorted(ports, key=lambda value: int(value[3:]))]


if __name__ == "__main__":
    print(json.dumps({"ports": list_ports()}, ensure_ascii=True))
