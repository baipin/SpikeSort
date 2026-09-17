import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BEST_EXPERIMENT = "s3-dynamic-tx-1472"

# When this file is launched as ``python tools/run_best_udp.py``, Python puts
# ``tools`` (rather than the repository root) on sys.path.  Add the root so
# the shared discovery helper is importable in both launch modes.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run(command, *, env=None):
    print()
    print(">", " ".join(str(part) for part in command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def idf_env():
    env = os.environ.copy()
    env.setdefault("IDF_PATH", r"E:\esp\v6.0.2\esp-idf")
    env.setdefault("IDF_TOOLS_PATH", r"E:\Espressif\tools")
    env.setdefault("ESP_ROM_ELF_DIR", r"E:\Espressif\tools\esp-rom-elfs\20241011")
    env.setdefault("ESP_IDF_VERSION", "6.0.2")
    env.setdefault("IDF_PYTHON_ENV_PATH", r"E:\Espressif\tools\python\v6.0.2\venv")
    tool_path = (
        r"E:\Espressif\tools\cmake\4.0.3\bin;"
        r"E:\Espressif\tools\ninja\1.12.1;"
        r"E:\Espressif\tools\xtensa-esp-elf\esp-15.2.0_20251204\xtensa-esp-elf\bin"
    )
    env["PATH"] = tool_path + ";" + env.get("PATH", "")
    env["IDF_TARGET"] = "esp32s3"
    return env


def default_idf_python():
    candidate = Path(r"E:\Espressif\tools\python\v6.0.2\venv\Scripts\python.exe")
    return str(candidate) if candidate.exists() else sys.executable


def discover_receiver_ip():
    """Use the shared Windows Wi-Fi discovery implementation."""
    from tools.flash_best_udp_auto import discover_local_ipv4

    return discover_local_ipv4()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build, flash, capture, report, and refresh the current best ESP32-S3 UDP profile."
    )
    parser.add_argument("--port", default="COM7")
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--startup-timeout-s", type=float, default=90.0)
    parser.add_argument("--condition-suffix", default="best-udp")
    parser.add_argument("--no-clean-build", action="store_true")
    parser.add_argument(
        "--receiver-high-priority",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use Windows high priority for the local UDP receiver (default: enabled).",
    )
    parser.add_argument(
        "--receiver-ip",
        help="Override the generated firmware receiver address for this run.",
    )
    parser.add_argument(
        "--strict-epoch-timestamps",
        action="store_true",
        help="Require SNTP/epoch timestamps. Throughput/loss sweeps usually allow monotonic timestamps.",
    )
    parser.add_argument(
        "--strict-send-success",
        action="store_true",
        help="Record successful UDP sends, export sender records, and compute post-send loss.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    command = [
        default_idf_python(),
        "tools/run_udp_throughput_matrix.py",
        "--only",
        BEST_EXPERIMENT,
        "--duration-s",
        str(args.duration_s),
        "--jobs",
        str(args.jobs),
        "--port",
        args.port,
        "--startup-timeout-s",
        str(args.startup_timeout_s),
        "--condition-suffix",
        args.condition_suffix,
    ]
    receiver_ip = args.receiver_ip or discover_receiver_ip()
    print(f"Using receiver IPv4 for this build: {receiver_ip}", flush=True)
    command.extend(["--receiver-ip", receiver_ip])
    if args.receiver_high_priority:
        command.append("--receiver-high-priority")
    if args.strict_send_success:
        command.append("--strict-send-success")
        command.extend(["--build-root", "build_udp_strict_120s"])
    if not args.no_clean_build:
        command.append("--clean-build")
    if args.strict_epoch_timestamps or args.strict_send_success:
        command.append("--require-epoch-timestamps")
    else:
        command.append("--allow-monotonic-timestamps")

    run(command, env=idf_env())


if __name__ == "__main__":
    main()
