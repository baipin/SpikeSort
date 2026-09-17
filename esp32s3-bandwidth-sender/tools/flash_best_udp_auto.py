"""Build and flash the best unlimited UDP profile using the local Wi-Fi IPv4.

The receiver address is written to a generated defaults file for this build;
the checked-in profile remains unchanged.
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DEFAULTS = PROJECT_ROOT / "sdkconfig.defaults.udp_max_throughput_s3_dynamic_tx_1472"
GENERATED_DEFAULTS = PROJECT_ROOT / "sdkconfig.generated.auto_local_ip"
SDKCONFIG = PROJECT_ROOT / "sdkconfig.auto_local_ip"
BUILD_DIR = PROJECT_ROOT / "build_artifacts" / "auto_local_ip_udp"
DEFAULT_IDF = Path(r"E:\esp\v6.0.2\esp-idf")
DEFAULT_PYTHON = Path(r"E:\Espressif\tools\python\v6.0.2\venv\Scripts\python.exe")


def discover_local_ipv4() -> str:
    """Return the preferred private IPv4 address from an active Wi-Fi adapter."""
    candidates: list[str] = []
    # PowerShell property names are stable across localized Windows versions.
    ps = (
        "Get-NetIPConfiguration | Where-Object { $_.NetAdapter.Status -eq 'Up' -and $_.IPv4Address } "
        "| ForEach-Object { $_.NetAdapter.InterfaceDescription + '|' + $_.IPv4Address.IPAddress }"
    )
    try:
        output = subprocess.check_output(["powershell", "-NoProfile", "-Command", ps],
                                         text=True, encoding="utf-8", errors="replace",
                                         stderr=subprocess.DEVNULL)
        for line in output.splitlines():
            description, _, raw = line.rpartition("|")
            if re.search(r"wi-?fi|wlan|wireless|无线", description, re.IGNORECASE):
                try:
                    address = ipaddress.ip_address(raw.strip())
                except ValueError:
                    continue
                if address.version == 4 and not address.is_loopback and not address.is_link_local:
                    candidates.append(str(address))
    except (OSError, subprocess.CalledProcessError):
        pass

    # Fallback for machines where the NetTCPIP cmdlets are unavailable.
    if not candidates:
        output = subprocess.check_output(["ipconfig"], text=True, encoding="oem", errors="replace")
        for block in re.split(r"\r?\n(?=\s*[^\r\n]*adapter\s+)", output, flags=re.IGNORECASE):
            if not re.search(r"wi-?fi|wlan|wireless|无线局域网", block, re.IGNORECASE):
                continue
            for raw in re.findall(r"(?:IPv4 Address|IPv4 地址)[^:]*:\s*([0-9.]+)", block, re.IGNORECASE):
                try:
                    address = ipaddress.ip_address(raw)
                except ValueError:
                    continue
                if address.version == 4 and not address.is_loopback and not address.is_link_local:
                    candidates.append(str(address))
    if not candidates:
        raise SystemExit("No active Wi-Fi IPv4 address found. Connect the receiver to the experiment Wi-Fi first.")
    if len(candidates) > 1:
        print(f"Multiple Wi-Fi IPv4 addresses found; using {candidates[0]}: {candidates}", flush=True)
    return candidates[0]


def idf_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("IDF_PATH", str(DEFAULT_IDF))
    env.setdefault("IDF_TOOLS_PATH", r"E:\Espressif\tools")
    env.setdefault("IDF_PYTHON_ENV_PATH", r"E:\Espressif\tools\python\v6.0.2\venv")
    env["IDF_TARGET"] = "esp32s3"
    env["PATH"] = (
        r"E:\Espressif\tools\cmake\4.0.3\bin;"
        r"E:\Espressif\tools\ninja\1.12.1;"
        r"E:\Espressif\tools\xtensa-esp-elf\esp-15.2.0_20251204\xtensa-esp-elf\bin;"
        + env.get("PATH", "")
    )
    return env


def idf_command() -> list[str]:
    idf_path = Path(os.environ.get("IDF_PATH", DEFAULT_IDF))
    idf_py = idf_path / "tools" / "idf.py"
    python = DEFAULT_PYTHON if DEFAULT_PYTHON.exists() else Path(sys.executable)
    if not idf_py.exists():
        raise SystemExit(f"Cannot find idf.py at {idf_py}. Open an ESP-IDF terminal or set IDF_PATH.")
    return [str(python), str(idf_py)]


def run(command: list[str], env: dict[str, str]) -> None:
    print(">", " ".join(command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def write_generated_defaults(receiver_ip: str) -> None:
    if not BASE_DEFAULTS.exists():
        raise SystemExit(f"Missing base defaults file: {BASE_DEFAULTS}")
    content = BASE_DEFAULTS.read_text(encoding="utf-8")
    replacement = f'CONFIG_BANDWIDTH_SERVER_IP="{receiver_ip}"'
    content = re.sub(r'^CONFIG_BANDWIDTH_SERVER_IP=.*$', replacement, content, flags=re.MULTILINE)
    # The field terminal needs sender-side 50 ms counters in addition to the
    # high-throughput profile, so its completed runs can report strict window
    # diagnostics without changing the datagram size.
    content += (
        "CONFIG_BANDWIDTH_50MS_TELEMETRY=y\n"
        "CONFIG_BANDWIDTH_EXTENDED_TELEMETRY=y\n"
    )
    GENERATED_DEFAULTS.write_text(content.rstrip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-detect the receiver IP, build, and flash unlimited UDP firmware.")
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--receiver-ip", help="Override automatic Wi-Fi IPv4 discovery.")
    parser.add_argument("--no-clean", action="store_true", help="Keep the existing generated build directory.")
    args = parser.parse_args()

    receiver_ip = args.receiver_ip or discover_local_ipv4()
    write_generated_defaults(receiver_ip)
    env = idf_environment()
    env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(args.jobs)
    if not args.no_clean and BUILD_DIR.exists():
        import shutil

        shutil.rmtree(BUILD_DIR)

    common = [
        *idf_command(),
        "-B",
        str(BUILD_DIR),
        "-D",
        f"SDKCONFIG={SDKCONFIG}",
        "-D",
        f"SDKCONFIG_DEFAULTS={GENERATED_DEFAULTS}",
    ]
    run([*common, "set-target", "esp32s3"], env)
    run([*common, "build"], env)
    run([*idf_command(), "-B", str(BUILD_DIR), "-p", args.port, "flash"], env)
    print(
        f"Flashed ESP32-S3 unlimited UDP firmware. Receiver IP={receiver_ip}, "
        "port=5001, payload=1472 bytes.",
        flush=True,
    )


if __name__ == "__main__":
    main()
