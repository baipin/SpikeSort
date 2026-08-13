import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command):
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

    raise SystemExit("matplotlib is required. Install it with: python -m pip install matplotlib")


def latest_capture(captures_root):
    candidates = [
        path
        for path in captures_root.glob("udp_*")
        if path.is_dir() and (path / "bandwidth_capture.sqlite3").exists()
    ]
    if not candidates:
        raise SystemExit(f"No UDP capture with bandwidth_capture.sqlite3 found under {captures_root}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def latest_packet_log(capture_dir):
    logs = sorted(capture_dir.glob("packet_log_*.csv"), key=lambda path: path.stat().st_mtime)
    if not logs:
        return None
    return logs[-1]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate the standard report and packet-log figures for a UDP capture."
    )
    parser.add_argument(
        "--capture-dir",
        help="Capture directory to process. Defaults to the newest captures/udp_* directory.",
    )
    parser.add_argument(
        "--manifest",
        default="experiments/udp_max_throughput.json",
        help="Experiment manifest used by the report generator.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    capture_dir = Path(args.capture_dir) if args.capture_dir else latest_capture(PROJECT_ROOT / "captures")
    if not capture_dir.is_absolute():
        capture_dir = PROJECT_ROOT / capture_dir
    capture_dir = capture_dir.resolve()

    sqlite_path = capture_dir / "bandwidth_capture.sqlite3"
    if not sqlite_path.exists():
        raise SystemExit(f"Missing SQLite capture database: {sqlite_path}")

    packet_log = latest_packet_log(capture_dir)
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

    if packet_log is not None:
        run(
            [
                py_for_reports,
                "tools/visualize_packet_log.py",
                str(packet_log),
                "--out-dir",
                str(capture_dir / "figures"),
            ]
        )
    else:
        print(f"No packet_log_*.csv found under {capture_dir}; skipped packet-log figures.", flush=True)

    run([py_for_reports, "tools/build_report_browser.py"])

    print()
    print("Done.")
    print(f"Capture directory: {capture_dir}")
    print("Open: reports/index.html")


if __name__ == "__main__":
    main()
