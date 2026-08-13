import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "experiments" / "udp_max_throughput.json"


def slugify(value):
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    if not value:
        raise SystemExit("Condition name becomes empty after sanitizing. Use letters, numbers, dashes, or underscores.")
    return value


def run(command):
    print()
    print(">", " ".join(str(part) for part in command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def python_has_matplotlib(python_exe):
    try:
        subprocess.run(
            [str(python_exe), "-c", "import matplotlib"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def report_python():
    candidates = [Path(sys.executable)]
    candidates.extend(
        [
            Path.home() / "AppData/Local/Programs/Python/Python313/python.exe",
            Path.home() / "AppData/Local/Programs/Python/Python312/python.exe",
            Path.home() / "AppData/Local/Programs/Python/Python311/python.exe",
        ]
    )

    for candidate in candidates:
        if candidate.exists() and python_has_matplotlib(candidate):
            if Path(sys.executable) != candidate:
                print(f"Using report Python with matplotlib: {candidate}", flush=True)
            return str(candidate)

    print(
        "matplotlib is not installed in the current Python environment. "
        "Install it with: python -m pip install matplotlib",
        flush=True,
    )
    return sys.executable


def run_receiver(command, capture_dir):
    print()
    print(">", " ".join(str(part) for part in command), flush=True)
    result = subprocess.run(command, cwd=PROJECT_ROOT)
    sqlite_path = capture_dir / "bandwidth_capture.sqlite3"
    if result.returncode != 0:
        if sqlite_path.exists():
            print(
                f"Receiver exited with code {result.returncode}, but capture data exists; "
                "continuing with report generation.",
                flush=True,
            )
        else:
            raise subprocess.CalledProcessError(result.returncode, command)


def latest_packet_log(capture_dir):
    logs = sorted(capture_dir.glob("packet_log_*.csv"))
    if not logs:
        raise SystemExit(f"No packet_log_*.csv was generated under {capture_dir}")
    return logs[-1]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run one battery ESP32-S3 UDP field test and generate reports/figures."
    )
    parser.add_argument(
        "--condition",
        required=True,
        help="Human-readable condition label, for example battery-3m-line-of-sight.",
    )
    parser.add_argument("--duration-s", type=float, default=300.0, help="Receiver duration in seconds.")
    parser.add_argument("--payload-bytes", type=int, default=1024)
    parser.add_argument("--target-fps", type=int, default=1000)
    parser.add_argument("--notes", default=None, help="Optional English note stored in the capture metadata.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--output-root", default="captures")
    parser.add_argument("--websocket", action="store_true", help="Enable receiver WebSocket output.")
    parser.add_argument("--influx", action="store_true", help="Enable receiver InfluxDB output.")
    parser.add_argument(
        "--skip-browser-refresh",
        action="store_true",
        help="Do not refresh reports/report_index.js after report generation.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    condition = slugify(args.condition)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    capture_dir = PROJECT_ROOT / args.output_root / f"udp_{condition}_{stamp}"
    experiment_id = f"udp-{condition}-{stamp}"

    print("Battery ESP32-S3 UDP field test")
    print(f"Condition: {condition}")
    print(f"Duration: {args.duration_s:.1f} s")
    print(f"Capture directory: {capture_dir}")
    print()
    print("Before continuing, confirm:")
    print("1. VPN is off.")
    print("2. Windows Mobile Hotspot is on.")
    print("3. ESP32-S3 is powered and placed in the target condition.")
    print("4. Press reset/power on the ESP32-S3 immediately after this receiver starts.")

    receiver_command = [
        sys.executable,
        "-u",
        "udp_receiver.py",
        "--manifest",
        args.manifest,
        "--experiment-id",
        experiment_id,
        "--condition",
        condition,
        "--payload-bytes",
        str(args.payload_bytes),
        "--target-fps",
        str(args.target_fps),
        "--duration-s",
        str(args.duration_s),
        "--output-dir",
        str(capture_dir),
    ]
    if args.notes:
        receiver_command.extend(["--notes", args.notes])
    if not args.websocket:
        receiver_command.append("--no-websocket")
    if not args.influx:
        receiver_command.append("--no-influx")

    run_receiver(receiver_command, capture_dir)

    packet_log = latest_packet_log(capture_dir)
    sqlite_path = capture_dir / "bandwidth_capture.sqlite3"
    if not sqlite_path.exists():
        raise SystemExit(f"No SQLite capture database was generated under {capture_dir}")
    py_for_reports = report_python()

    run(
        [
            py_for_reports,
            "tools/generate_report.py",
            "--db",
            str(sqlite_path),
            "--out",
            "reports",
            "--manifest",
            args.manifest,
        ]
    )

    run(
        [
            py_for_reports,
            "tools/visualize_packet_log.py",
            str(packet_log),
            "--out-dir",
            str(capture_dir / "figures"),
        ]
    )

    if not args.skip_browser_refresh:
        run([py_for_reports, "tools/build_report_browser.py"])

    print()
    print("Done.")
    print(f"Capture directory: {capture_dir}")
    print(f"SQLite capture: {sqlite_path}")
    print(f"Packet log: {packet_log}")
    print("Markdown reports: reports/bandwidth_report_*.md")
    print("CSV summaries: reports/bandwidth_summary_*.csv")
    print("Report figures: reports/figures/")
    print(f"Packet-log figures: {capture_dir / 'figures'}")
    print("Open local report browser: reports/index.html")


if __name__ == "__main__":
    main()
