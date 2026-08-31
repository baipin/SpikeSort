import argparse
import csv
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "experiments" / "udp_max_throughput.json"
LOG_DIR = PROJECT_ROOT / "logs"


EXPERIMENTS = [
    {
        "name": "s3-dynamic-tx-1024",
        "defaults": "sdkconfig.defaults.udp_max_throughput_s3_dynamic_tx_1024",
        "payload_bytes": 1024,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP max-throughput: dynamic TX buffers, lwIP IRAM, 1024-byte payload, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472",
        "defaults": "sdkconfig.defaults.udp_max_throughput_s3_dynamic_tx_1472",
        "payload_bytes": 1472,
        "target_fps": "unlimited",
        "skip_crc": True,
        "notes": "ESP32-S3 UDP max-throughput: iperf-like blocking UDP fast path, dynamic TX buffers, lwIP IRAM, 1472-byte payload, static payload, CRC disabled, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-800fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_800fps",
        "payload_bytes": 1472,
        "target_fps": 800,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 800 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-300fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_300fps",
        "payload_bytes": 1472,
        "target_fps": 300,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 300 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-275fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_275fps",
        "payload_bytes": 1472,
        "target_fps": 275,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 275 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-250fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_250fps",
        "payload_bytes": 1472,
        "target_fps": 250,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 250 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-200fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_200fps",
        "payload_bytes": 1472,
        "target_fps": 200,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 200 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-1200fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_1200fps",
        "payload_bytes": 1472,
        "target_fps": 1200,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP loss-reduction sweep: 1472-byte payload, 1200 fps, static payload, CRC disabled, deferred receiver storage.",
    },
    {
        "name": "s3-iperfopt-1472-1000fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_1472_1000fps",
        "payload_bytes": 1472,
        "target_fps": 1000,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization: official iperf WiFi/lwIP defaults, 1472-byte payload, 1000 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-iperfopt-1472-1100fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_1472_1100fps",
        "payload_bytes": 1472,
        "target_fps": 1100,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization: official iperf WiFi/lwIP defaults, 1472-byte payload, 1100 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-iperfopt-1472-1200fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_1472_1200fps",
        "payload_bytes": 1472,
        "target_fps": 1200,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization: official iperf WiFi/lwIP defaults, 1472-byte payload, 1200 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-iperfopt-1472-1250fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_1472_1250fps",
        "payload_bytes": 1472,
        "target_fps": 1250,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization: official iperf WiFi/lwIP defaults, 1472-byte payload, 1250 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-iperfopt-1472-1300fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_1472_1300fps",
        "payload_bytes": 1472,
        "target_fps": 1300,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization: official iperf WiFi/lwIP defaults, 1472-byte payload, 1300 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-iperfopt-tx96-1472-1300fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_tx96_1472_1300fps",
        "payload_bytes": 1472,
        "target_fps": 1300,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization with 96 dynamic WiFi TX buffers, 1472-byte payload, 1300 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-iperfopt-tx96-1472-1350fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_tx96_1472_1350fps",
        "payload_bytes": 1472,
        "target_fps": 1350,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization with 96 dynamic WiFi TX buffers, 1472-byte payload, 1350 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-iperfopt-tx96-1472-1325fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_tx96_1472_1325fps",
        "payload_bytes": 1472,
        "target_fps": 1325,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization with 96 dynamic WiFi TX buffers, 1472-byte payload, 1325 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-iperfopt-tx96-1472-1400fps",
        "defaults": "sdkconfig.defaults.udp_s3_iperfopt_tx96_1472_1400fps",
        "payload_bytes": 1472,
        "target_fps": 1400,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP iperf-like optimization with 96 dynamic WiFi TX buffers, 1472-byte payload, 1400 fps, static payload, CRC disabled.",
    },
    {
        "name": "s3-dynamic-tx-1472-1500fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_1500fps",
        "payload_bytes": 1472,
        "target_fps": 1500,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP loss-reduction sweep: 1472-byte payload, 1500 fps, static payload, CRC disabled, deferred receiver storage.",
    },
    {
        "name": "s3-dynamic-tx-1472-1800fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_1800fps",
        "payload_bytes": 1472,
        "target_fps": 1800,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP loss-reduction sweep: 1472-byte payload, 1800 fps, static payload, CRC disabled, deferred receiver storage.",
    },
    {
        "name": "s3-dynamic-tx-1472-2100fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_2100fps",
        "payload_bytes": 1472,
        "target_fps": 2100,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP loss-reduction sweep: 1472-byte payload, 2100 fps, static payload, CRC disabled, deferred receiver storage.",
    },
    {
        "name": "s3-dynamic-tx-1472-2400fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_2400fps",
        "payload_bytes": 1472,
        "target_fps": 2400,
        "skip_crc": True,
        "notes": "ESP32-S3 UDP loss-reduction sweep: 1472-byte payload, 2400 fps, static payload, CRC disabled, deferred receiver storage.",
    },
    {
        "name": "s3-dynamic-tx-1472-400fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_400fps",
        "payload_bytes": 1472,
        "target_fps": 400,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 400 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-400fps-fresh",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_400fps_fresh",
        "payload_bytes": 1472,
        "target_fps": 400,
        "skip_crc": False,
        "notes": "ESP32-S3 freshness-first paced UDP: 400 fps, precise pacing, and stale-slot dropping after one late frame interval.",
    },
    {
        "name": "s3-dynamic-tx-1472-600fps-fresh",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_600fps_fresh",
        "payload_bytes": 1472,
        "target_fps": 600,
        "skip_crc": False,
        "notes": "ESP32-S3 freshness-first paced UDP: 600 fps, precise pacing, and stale-slot dropping after one late frame interval.",
    },
    {
        "name": "s3-400-na",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_400fps_fresh_noampdu",
        "payload_bytes": 1472,
        "target_fps": 400,
        "skip_crc": False,
        "notes": "ESP32-S3 freshness-first paced UDP: 400 fps with sender TX AMPDU disabled to diagnose receive-side burst latency.",
    },
    {
        "name": "s3-dynamic-tx-1472-350fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_350fps",
        "payload_bytes": 1472,
        "target_fps": 350,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 350 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-500fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_500fps",
        "payload_bytes": 1472,
        "target_fps": 500,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 500 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-600fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_600fps",
        "payload_bytes": 1472,
        "target_fps": 600,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 600 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-850fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_850fps",
        "payload_bytes": 1472,
        "target_fps": 850,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 850 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-900fps",
        "defaults": "sdkconfig.defaults.udp_s3_dynamic_tx_1472_900fps",
        "payload_bytes": 1472,
        "target_fps": 900,
        "skip_crc": False,
        "notes": "ESP32-S3 UDP controlled-throughput: dynamic TX buffers, lwIP IRAM, 1472-byte payload, 900 fps, 11g/n, HT20.",
    },
    {
        "name": "s3-dynamic-tx-1472-nocrc",
        "defaults": "sdkconfig.defaults.udp_max_throughput_s3_dynamic_tx_1472_nocrc",
        "payload_bytes": 1472,
        "target_fps": "unlimited",
        "skip_crc": True,
        "notes": "ESP32-S3 UDP diagnostic: dynamic TX buffers, lwIP IRAM, 1472-byte payload, static payload, CRC disabled.",
    },
]


def run(command, *, check=True, env=None, log_handle=None):
    print()
    print(">", " ".join(str(part) for part in command), flush=True)
    if log_handle:
        log_handle.write("\n> " + " ".join(str(part) for part in command) + "\n")
        log_handle.flush()

    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        try:
            print(line, end="", flush=True)
        except OSError:
            # Some Windows consoles reject occasional redirected serial output.
            # Keep logging to file so long-running experiments can still finish.
            pass
        if log_handle:
            log_handle.write(line)
    returncode = process.wait()
    if log_handle:
        log_handle.flush()

    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, command)
    return subprocess.CompletedProcess(command, returncode)


def idf_command(*args):
    idf_path = os.environ.get("IDF_PATH")
    if idf_path:
        idf_py = Path(idf_path) / "tools" / "idf.py"
        if idf_py.exists():
            return [sys.executable, str(idf_py), *args]
    return [sys.executable, "-m", "idf_component_tools.sources.idf", *args]


def idf_env(target, jobs=None):
    env = os.environ.copy()
    env.setdefault("IDF_TOOLS_PATH", r"E:\Espressif\tools")
    env.setdefault("ESP_ROM_ELF_DIR", r"E:\Espressif\tools\esp-rom-elfs\20241011")
    env["IDF_TARGET"] = target
    if jobs is not None:
        env["CMAKE_BUILD_PARALLEL_LEVEL"] = str(jobs)
    return env


def clean_build_dir(build_dir):
    build_path = (PROJECT_ROOT / build_dir).resolve()
    project_root = PROJECT_ROOT.resolve()
    if not build_path.is_relative_to(project_root):
        raise SystemExit(f"Refusing to clean build directory outside project: {build_path}")
    if build_path.exists():
        print(f"Cleaning generated build directory: {build_path}", flush=True)
        shutil.rmtree(build_path)


def set_generated_receiver_ip(sdkconfig_name, receiver_ip):
    """Update only the generated sdkconfig value used by this experiment."""
    if not receiver_ip:
        return
    sdkconfig_path = PROJECT_ROOT / sdkconfig_name
    if not sdkconfig_path.exists():
        raise SystemExit(f"Generated sdkconfig not found: {sdkconfig_path}")
    lines = sdkconfig_path.read_text(encoding="utf-8", errors="replace").splitlines()
    replacement = f'CONFIG_BANDWIDTH_SERVER_IP="{receiver_ip}"'
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith("CONFIG_BANDWIDTH_SERVER_IP="):
            lines[index] = replacement
            replaced = True
            break
    if not replaced:
        lines.append(replacement)
    sdkconfig_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_generated_config_values(sdkconfig_name, values):
    """Override a small set of generated sdkconfig values for one run."""
    sdkconfig_path = PROJECT_ROOT / sdkconfig_name
    lines = sdkconfig_path.read_text(encoding="utf-8", errors="replace").splitlines()
    rendered = {}
    for key, value in values.items():
        if isinstance(value, bool):
            rendered[key] = f"CONFIG_{key}=y" if value else f"# CONFIG_{key} is not set"
        else:
            rendered[key] = f"CONFIG_{key}={value}"
    replaced = set()
    for index, line in enumerate(lines):
        for key, replacement in rendered.items():
            if line.startswith(f"CONFIG_{key}=") or line == f"# CONFIG_{key} is not set":
                lines[index] = replacement
                replaced.add(key)
                break
    for key, replacement in rendered.items():
        if key not in replaced:
            lines.append(replacement)
    sdkconfig_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_defaults_override(base_defaults, name, values):
    """Create a complete defaults file so sdkconfig is final before CMake configures."""
    base_path = PROJECT_ROOT / base_defaults
    override_path = PROJECT_ROOT / f"sdkconfig.generated.{name}"
    text = base_path.read_text(encoding="utf-8", errors="replace").rstrip() + "\n\n"
    for key, value in values.items():
        if isinstance(value, bool):
            text += f"CONFIG_{key}=y\n" if value else f"# CONFIG_{key} is not set\n"
        else:
            text += f"CONFIG_{key}={value}\n"
    override_path.write_text(text, encoding="utf-8")
    return str(override_path)


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
            return str(candidate)
    return sys.executable


def latest_report_summary():
    summaries = sorted((PROJECT_ROOT / "reports").rglob("bandwidth_summary_*.csv"))
    if not summaries:
        return None, {}
    path = summaries[-1]
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return path, rows[0] if rows else {}


def latest_packet_log(capture_dir):
    logs = sorted(capture_dir.glob("packet_log_*.csv"), key=lambda path: path.stat().st_mtime)
    return logs[-1] if logs else None


def validate_sntp_defaults(defaults_name, *, allow_monotonic_timestamps=False):
    defaults_path = PROJECT_ROOT / defaults_name
    if not defaults_path.exists():
        raise SystemExit(f"Missing sdkconfig defaults: {defaults_path}")

    text = defaults_path.read_text(encoding="utf-8", errors="replace")
    required_lines = {
        "CONFIG_BANDWIDTH_SNTP_ENABLE=y": "SNTP must be enabled for epoch-aligned latency timestamps.",
    }
    if not allow_monotonic_timestamps:
        required_lines["CONFIG_BANDWIDTH_REQUIRE_SNTP=y"] = (
            "SNTP must be required so firmware does not fall back to monotonic timestamps."
        )
    for line, message in required_lines.items():
        if line not in text:
            raise SystemExit(f"{defaults_path.name}: {message} Add {line}.")


def run_one(exp, args, log_handle):
    validate_sntp_defaults(exp["defaults"], allow_monotonic_timestamps=args.allow_monotonic_timestamps)

    capture_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    condition = f"{exp['name']}-{args.condition_suffix}".strip("-")
    capture_dir = PROJECT_ROOT / args.output_root / f"udp_{condition}_{capture_stamp}"
    sdkconfig = f"sdkconfig.exp.{exp['name']}"
    build_dir = str((PROJECT_ROOT / args.build_root / f"build_exp_{exp['name']}").resolve())

    effective_defaults = exp["defaults"]
    if args.strict_send_success or args.receiver_ip:
        overrides = {}
        if args.strict_send_success:
            overrides.update(
                {
                    "BANDWIDTH_UDP_BLOCKING_FAST_SEND": False,
                    "BANDWIDTH_RECORD_SEND_SUCCESSES": True,
                    "BANDWIDTH_TEST_DURATION_S": int(args.duration_s),
                    "BANDWIDTH_SEND_RECORD_CAPACITY": 250000,
                }
            )
        if args.receiver_ip:
            overrides["BANDWIDTH_SERVER_IP"] = f'"{args.receiver_ip}"'
        effective_defaults = make_defaults_override(exp["defaults"], exp["name"], overrides)

    common_idf_args = [
        "-B",
        build_dir,
        "-D",
        f"SDKCONFIG={sdkconfig}",
        "-D",
        f"SDKCONFIG_DEFAULTS={effective_defaults}",
    ]

    idf_child_env = idf_env(args.target, args.jobs)
    if args.clean_build:
        clean_build_dir(build_dir)

    if not args.skip_set_target:
        run(
            idf_command(
                *common_idf_args,
                "set-target",
                args.target,
            ),
            env=idf_child_env,
            log_handle=log_handle,
        )
    run(
        idf_command(
            *common_idf_args,
            "build",
        ),
        env=idf_child_env,
        log_handle=log_handle,
    )
    run(idf_command("-B", build_dir, "-p", args.port, "flash"), env=idf_child_env, log_handle=log_handle)

    serial_capture = None
    serial_log_path = capture_dir / "sender_monitor.txt"
    if args.strict_send_success:
        serial_capture = subprocess.Popen(
            [
                sys.executable,
                "tools/capture_sender_serial_log.py",
                "--port",
                args.port,
                "--baud",
                "921600",
                "--duration-s",
                str(max(args.duration_s + 120.0, 180.0)),
                "--out",
                str(serial_log_path),
            ],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

    receiver_cmd = [
        sys.executable,
        "-u",
        "udp_receiver.py",
        "--manifest",
        str(args.manifest),
        "--experiment-id",
        f"udp-{condition}-{capture_stamp}",
        "--condition",
        condition,
        "--payload-bytes",
        str(exp["payload_bytes"]),
        "--target-fps",
        str(exp.get("target_fps") if exp.get("target_fps") != "unlimited" else args.target_fps),
        "--socket-rcvbuf",
        str(exp.get("socket_rcvbuf", args.socket_rcvbuf)),
        "--duration-s",
        str(args.duration_s),
        "--startup-timeout-s",
        str(args.startup_timeout_s),
        "--output-dir",
        str(capture_dir),
        "--notes",
        exp["notes"],
        "--no-websocket",
        "--no-influx",
        "--defer-frame-storage",
    ]
    if exp["skip_crc"]:
        receiver_cmd.append("--skip-crc")
    if args.receiver_high_priority:
        receiver_cmd.append("--high-priority")
    if args.require_epoch_timestamps:
        receiver_cmd.append("--require-epoch-timestamps")
    try:
        run(receiver_cmd, log_handle=log_handle)
    finally:
        if serial_capture is not None:
            try:
                serial_capture.wait(timeout=120)
            except subprocess.TimeoutExpired:
                serial_capture.terminate()
                serial_capture.wait(timeout=10)

    sqlite_path = capture_dir / "bandwidth_capture.sqlite3"
    if not sqlite_path.exists():
        raise SystemExit(f"Missing capture database: {sqlite_path}")

    py_for_reports = report_python()
    run([py_for_reports, "tools/generate_report.py", "--db", str(sqlite_path), "--out", "reports", "--manifest", str(args.manifest)], log_handle=log_handle)
    packet_log = latest_packet_log(capture_dir)
    if packet_log is not None:
        run(
            [
                py_for_reports,
                "tools/visualize_packet_log.py",
                str(packet_log),
                "--out-dir",
                str(capture_dir / "figures"),
            ],
            log_handle=log_handle,
        )
        if args.strict_send_success and serial_log_path.exists():
            sender_success_csv = capture_dir / "sender_success.csv"
            run(
                [sys.executable, "tools/extract_send_success_log.py", str(serial_log_path), "--out", str(sender_success_csv)],
                log_handle=log_handle,
            )
            run(
                [
                    sys.executable,
                    "tools/analyze_post_send_udp_loss.py",
                    "--sender-success",
                    str(sender_success_csv),
                    "--packet-log",
                    str(packet_log),
                    "--out",
                    str(capture_dir / "post_send_udp_loss.json"),
                    "--summary-csv",
                    str(capture_dir / "post_send_udp_loss.csv"),
                ],
                log_handle=log_handle,
            )
            run(
                [
                    py_for_reports,
                    "tools/build_udp_send_timestamp_windows.py",
                    str(capture_dir),
                    "--window-ms",
                    "50",
                    "--frame-bytes",
                    str(exp["payload_bytes"] + 14),
                ],
                log_handle=log_handle,
            )
    else:
        print(f"No packet_log_*.csv found under {capture_dir}; skipped packet-log figures.", flush=True)
        log_handle.write(f"No packet_log_*.csv found under {capture_dir}; skipped packet-log figures.\n")
    run([py_for_reports, "tools/build_report_browser.py"], log_handle=log_handle)

    summary_path, row = latest_report_summary()
    return {
        "experiment": exp["name"],
        "capture_dir": str(capture_dir),
        "summary_path": str(summary_path or ""),
        "mean_kib_s": row.get("rate_kib_s_mean", ""),
        "mean_mbps": (float(row["rate_kib_s_mean"]) * 8 / 1024) if row.get("rate_kib_s_mean") else "",
        "mean_loss_rate": row.get("loss_rate_mean", ""),
        "max_loss_rate": row.get("loss_rate_max", ""),
        "latency_count": row.get("latency_count", ""),
        "crc_errors": row.get("crc_errors_total", ""),
        "payload_bytes": exp["payload_bytes"],
        "target_fps": exp.get("target_fps", args.target_fps),
        "skip_crc": exp["skip_crc"],
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Build, flash, and run a short ESP32-S3 UDP throughput experiment matrix.")
    parser.add_argument("--port", default="COM7", help="ESP32-S3 serial port.")
    parser.add_argument("--target", default="esp32s3")
    parser.add_argument("--jobs", type=int, default=2, help="Parallel build jobs for ESP-IDF/CMake/Ninja.")
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--startup-timeout-s", type=float, default=30.0)
    parser.add_argument("--target-fps", type=int, default=1000)
    parser.add_argument("--socket-rcvbuf", type=int, default=4 * 1024 * 1024)
    parser.add_argument(
        "--receiver-high-priority",
        action="store_true",
        help="Request Windows high priority for udp_receiver.py during a scheduling diagnostic.",
    )
    parser.add_argument(
        "--receiver-ip",
        help="Override CONFIG_BANDWIDTH_SERVER_IP in the generated sdkconfig for this run.",
    )
    parser.add_argument("--condition-suffix", default="near")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-root", default="captures")
    parser.add_argument(
        "--build-root",
        default="build_artifacts/udp_matrix",
        help="Root for generated experiment builds. Use a fresh writable directory when an archived build is locked.",
    )
    parser.add_argument("--only", choices=[exp["name"] for exp in EXPERIMENTS], help="Run just one experiment.")
    parser.add_argument(
        "--preset",
        choices=["stable-sweep", "loss-reduction", "iperfopt"],
        help="Run a curated experiment set. stable-sweep tests low-loss paced UDP; loss-reduction tests 1200-2400 fps; iperfopt tests official iperf-like 1000-1200 fps.",
    )
    parser.add_argument(
        "--skip-set-target",
        action="store_true",
        help="Skip idf.py set-target and let idf.py build configure the project with IDF_TARGET from the child environment.",
    )
    parser.add_argument(
        "--clean-build",
        action="store_true",
        help="Remove the generated experiment build directory before building. Use this after Python, IDF, or defaults changes.",
    )
    parser.add_argument(
        "--require-epoch-timestamps",
        action="store_true",
        help="Abort the capture if UDP frames do not carry epoch-aligned timestamps for latency analysis.",
    )
    parser.add_argument(
        "--allow-monotonic-timestamps",
        action="store_true",
        help="Allow firmware to stream after SNTP timeout. Use only for throughput/loss sweeps, not latency reports.",
    )
    parser.add_argument(
        "--strict-send-success",
        action="store_true",
        help="Enable sender success recording, capture its serial export, and compute post-send UDP path loss.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"udp_throughput_matrix_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    if args.only and args.preset:
        raise SystemExit("--only and --preset are mutually exclusive")
    if args.preset == "stable-sweep":
        preset_names = {
            "s3-dynamic-tx-1472-200fps",
            "s3-dynamic-tx-1472-250fps",
            "s3-dynamic-tx-1472-275fps",
            "s3-dynamic-tx-1472-300fps",
            "s3-dynamic-tx-1472-350fps",
            "s3-dynamic-tx-1472-400fps",
            "s3-dynamic-tx-1472-500fps",
            "s3-dynamic-tx-1472-600fps",
        }
        selected = [exp for exp in EXPERIMENTS if exp["name"] in preset_names]
    elif args.preset == "loss-reduction":
        preset_names = {
            "s3-dynamic-tx-1472-1200fps",
            "s3-dynamic-tx-1472-1500fps",
            "s3-dynamic-tx-1472-1800fps",
            "s3-dynamic-tx-1472-2100fps",
            "s3-dynamic-tx-1472-2400fps",
        }
        selected = [exp for exp in EXPERIMENTS if exp["name"] in preset_names]
    elif args.preset == "iperfopt":
        preset_names = {
            "s3-iperfopt-1472-1000fps",
            "s3-iperfopt-1472-1100fps",
            "s3-iperfopt-1472-1200fps",
            "s3-iperfopt-1472-1250fps",
            "s3-iperfopt-1472-1300fps",
            "s3-iperfopt-tx96-1472-1300fps",
            "s3-iperfopt-tx96-1472-1325fps",
            "s3-iperfopt-tx96-1472-1350fps",
            "s3-iperfopt-tx96-1472-1400fps",
        }
        selected = [exp for exp in EXPERIMENTS if exp["name"] in preset_names]
    else:
        selected = [exp for exp in EXPERIMENTS if args.only in (None, exp["name"])]
    results = []
    with log_path.open("w", encoding="utf-8") as log_handle:
        print(f"Writing command log: {log_path}")
        for exp in selected:
            results.append(run_one(exp, args, log_handle))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_dir = PROJECT_ROOT / "reports" / "udp_matrices"
    result_dir.mkdir(parents=True, exist_ok=True)
    result_path = result_dir / f"udp_throughput_matrix_{stamp}.csv"
    with result_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print()
    print(f"Wrote matrix summary: {result_path}")
    for row in results:
        print(
            f"{row['experiment']}: {row['mean_kib_s']} KiB/s, "
            f"{row['mean_mbps']:.2f} Mbps, mean_loss={row['mean_loss_rate']}, "
            f"max_loss={row['max_loss_rate']}, latency_count={row['latency_count']}, crc={row['crc_errors']}"
        )


if __name__ == "__main__":
    main()
