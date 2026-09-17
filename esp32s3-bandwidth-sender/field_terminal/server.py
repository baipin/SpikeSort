import json
import os
import subprocess
import sys
import threading
import time
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).resolve().parent
CAPTURE_ROOT = ROOT / "captures" / "udp_battery_position_series_20260901"
DEFAULT_DATASET = "dataset1"
MARKERS_PATH = WEB / "markers.json"
PORT = 8765

state = {"process": None, "flash_process": None, "started": None, "capture_started": None,
         "duration": 0, "condition": "", "capture": "", "operation": "idle", "log": [], "summary": None}
lock = threading.RLock()


def add_log(message):
    with lock:
        state["log"].append(time.strftime("%H:%M:%S ") + message)
        state["log"] = state["log"][-80:]


def safe_name(value, fallback):
    name = "-".join(str(value or fallback).split())
    name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in name)
    return name.strip("-_") or fallback


def dataset_path(name):
    path = (CAPTURE_ROOT / safe_name(name, DEFAULT_DATASET)).resolve()
    if path.parent != CAPTURE_ROOT.resolve():
        raise RuntimeError("Invalid dataset name")
    return path


def dataset_listing():
    CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
    result = []
    for path in sorted((p for p in CAPTURE_ROOT.iterdir() if p.is_dir()), key=lambda p: p.name.lower()):
        runs = sorted((p.parent for p in path.glob("*/packet_log_*.csv")), key=lambda p: p.name)
        result.append({"name": path.name, "runs": [{"name": run.name, "path": str(run.relative_to(CAPTURE_ROOT))} for run in runs]})
    return result


def create_dataset(name):
    path = dataset_path(name)
    path.mkdir(parents=True, exist_ok=True)
    return path.name


def assign_run(run_rel, dataset):
    source = (CAPTURE_ROOT / Path(run_rel)).resolve()
    if CAPTURE_ROOT.resolve() not in source.parents or not (source / "field_metadata.json").exists():
        raise RuntimeError("Invalid experiment directory")
    destination_root = dataset_path(dataset)
    destination_root.mkdir(parents=True, exist_ok=True)
    destination = destination_root / source.name
    if destination.exists():
        raise RuntimeError("Destination experiment already exists")
    import shutil
    shutil.move(str(source), str(destination))
    return str(destination.relative_to(CAPTURE_ROOT))


def run_metadata(run_rel):
    capture = (CAPTURE_ROOT / Path(run_rel)).resolve()
    if CAPTURE_ROOT.resolve() not in capture.parents:
        raise RuntimeError("Invalid experiment directory")
    metadata = capture / "field_metadata.json"
    if not metadata.exists():
        raise RuntimeError("Experiment metadata is unavailable")
    return json.loads(metadata.read_text(encoding="utf-8"))


def run_summary(run_rel):
    capture = (CAPTURE_ROOT / Path(run_rel)).resolve()
    if CAPTURE_ROOT.resolve() not in capture.parents or not capture.is_dir():
        raise RuntimeError("Invalid experiment directory")
    return summarize_capture(capture)


def pump(process):
    for line in process.stdout:
        message = line.rstrip()
        add_log(message)
        if "CAPTURE_STARTED" in message:
            with lock:
                if state["capture_started"] is None:
                    state["capture_started"] = time.time()
    code = process.wait()
    add_log(f"Receiver exited with code {code}")
    capture = Path(state["capture"]) if state["capture"] else None
    summary = summarize_capture(capture) if code == 0 and capture else None
    with lock:
        state["process"] = None
        state["operation"] = "idle"
        state["summary"] = summary


def summarize_capture(capture):
    """Produce a compact, receiver-side summary for the operator UI."""
    try:
        packet_log = next(capture.glob("packet_log_*.csv"))
        metrics_log = next(capture.glob("metrics_*.csv"))
        with packet_log.open(encoding="utf-8", newline="") as handle:
            packets = [(int(row["recv_time_ns"]), int(row["seq"])) for row in csv.DictReader(handle)]
        if not packets:
            return {"error": "No UDP packets were captured."}
        packets.sort()
        start_ns, end_ns = packets[0][0], packets[-1][0]
        window_count = int((end_ns - start_ns) // 50_000_000) + 1
        window_packets = [0] * window_count
        for recv_ns, _ in packets:
            window_packets[(recv_ns - start_ns) // 50_000_000] += 1
        unique_seq = {seq for _, seq in packets}
        seq_span = max(unique_seq) - min(unique_seq) + 1
        with metrics_log.open(encoding="utf-8", newline="") as handle:
            metric_rows = list(csv.DictReader(handle))
        rates = [float(row["rate_kib_s"]) for row in metric_rows if row.get("rate_kib_s")]
        losses = [float(row["loss_rate"]) for row in metric_rows if row.get("loss_rate")]
        quality_path = capture / "capture_quality.json"
        quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
        empty = sum(count == 0 for count in window_packets)
        with packet_log.open(encoding="utf-8", newline="") as handle:
            send_times_us = [int(row["send_ts_us"]) for row in csv.DictReader(handle)]
        send_start, send_end = min(send_times_us), max(send_times_us)
        send_windows = int((send_end - send_start) // 50_000) + 1
        send_empty = send_windows - len({(value - send_start) // 50_000 for value in send_times_us})
        return {
            "capture": str(capture),
            "packets": len(packets),
            "duration_s": round((end_ns - start_ns) / 1_000_000_000, 3),
            "mean_mbps": round((sum(rates) / len(rates)) * 8 / 1024, 3) if rates else None,
            "empty_50ms": empty,
            "windows_50ms": window_count,
            "empty_50ms_pct": round(empty * 100 / window_count, 3),
            "esp32_empty_50ms": send_empty,
            "esp32_windows_50ms": send_windows,
            "esp32_empty_50ms_pct": round(send_empty * 100 / send_windows, 3),
            "sequence_gap_pct": round((seq_span - len(unique_seq)) * 100 / seq_span, 3),
            "mean_receiver_loss_pct": round((sum(losses) / len(losses)) * 100, 3) if losses else None,
            "sender_telemetry_available": bool(quality.get("sender_telemetry_available")),
        }
    except (OSError, StopIteration, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {"error": f"Could not summarize capture: {exc}"}


def latest_capture_dir():
    """Find the newest completed field capture for initial page rendering."""
    logs = list(CAPTURE_ROOT.rglob("packet_log_*.csv"))
    return max(logs, key=lambda path: path.stat().st_mtime).parent if logs else None


def pump_flash(process):
    for line in process.stdout:
        add_log("FLASH " + line.rstrip())
    code = process.wait()
    add_log(f"Flash operation exited with code {code}")
    with lock:
        state["flash_process"] = None
        state["operation"] = "idle"


def start_flash(port):
    port = str(port or "COM7").strip().upper()
    if not (port.startswith("COM") and port[3:].isdigit()):
        raise RuntimeError("Invalid serial port. Use a value such as COM7")
    with lock:
        if state["process"] is not None and state["process"].poll() is None:
            raise RuntimeError("Stop the active experiment before flashing")
        if state["flash_process"] is not None and state["flash_process"].poll() is None:
            raise RuntimeError("A flash operation is already running")
        command = [sys.executable, "tools/flash_best_udp_auto.py", "--port", port]
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", env=env)
        state.update({"flash_process": process, "operation": "flashing", "log": []})
        threading.Thread(target=pump_flash, args=(process,), daemon=True).start()


def start_run(payload):
    with lock:
        if state["process"] is not None and state["process"].poll() is None:
            raise RuntimeError("An experiment is already running")
        if state["flash_process"] is not None and state["flash_process"].poll() is None:
            raise RuntimeError("Wait for the flash operation to finish")
        duration = max(1, min(3600, int(payload.get("duration_s", 300))))
        condition = "-".join(str(payload.get("condition", "field-run")).split()) or "field-run"
        condition = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in condition)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        markers = json.loads(MARKERS_PATH.read_text(encoding="utf-8")) if MARKERS_PATH.exists() else {}
        missing_markers = [name for name in ("board", "router", "receiver") if name not in markers]
        if missing_markers:
            raise RuntimeError("Place all three map markers before starting: " + ", ".join(missing_markers))
        dataset = safe_name(payload.get("dataset"), DEFAULT_DATASET)
        dataset_root = dataset_path(dataset)
        dataset_root.mkdir(parents=True, exist_ok=True)
        capture = dataset_root / f"udp-telemetry-{condition}_{stamp}"
        capture.mkdir(parents=True, exist_ok=True)
        field_metadata = {
            "schema_version": 1,
            "experiment_id": f"udp-telemetry-{condition}-{stamp}",
            "capture_started_by_terminal_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "condition": condition,
            "dataset": dataset,
            "duration_s": duration,
            "hardware": str(payload.get("hardware", "ESP32-S3")),
            "power": str(payload.get("power", "battery / power bank")),
            "placement": str(payload.get("placement", "")),
            "distance": str(payload.get("distance", "")),
            "notes": str(payload.get("notes", "")),
            "markers": {key: value for key, value in markers.items() if key in ("board", "router", "receiver")},
        }
        (capture / "field_metadata.json").write_text(json.dumps(field_metadata, indent=2, ensure_ascii=True), encoding="utf-8")
        command = [
            sys.executable, "udp_receiver.py", "--manifest", str(ROOT / "experiments" / "udp_max_throughput.json"),
            "--experiment-id", f"udp-telemetry-{condition}-{stamp}", "--condition", condition,
            "--payload-bytes", "1472", "--target-fps", "1000", "--socket-rcvbuf", str(4 * 1024 * 1024),
            "--duration-s", str(duration), "--startup-timeout-s", "120", "--arm-delay-s", "15",
            "--output-dir", str(capture), "--notes", str(payload.get("notes", "")),
            "--no-websocket", "--no-influx", "--defer-frame-storage", "--skip-crc", "--high-priority",
        ]
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", env=env)
        state.update({"process": process, "started": time.time(), "capture_started": None, "duration": duration,
                      "condition": condition, "capture": str(capture), "operation": "experiment", "log": [], "summary": None})
        thread = threading.Thread(target=pump, args=(process,), daemon=True)
        thread.start()


def delete_latest_run(delete_build=False):
    with lock:
        process = state["process"]
        if process is not None and process.poll() is None:
            raise RuntimeError("Stop the active experiment before deleting a run")
    runs = sorted((path.parent for path in CAPTURE_ROOT.rglob("packet_log_*.csv")), key=lambda path: path.stat().st_mtime, reverse=True)
    if not runs:
        raise RuntimeError("No telemetry experiment directory exists")
    target = runs[0].resolve()
    if CAPTURE_ROOT.resolve() not in target.parents:
        raise RuntimeError("Refusing to delete a path outside the telemetry capture root")
    stamp = target.name.rsplit("_", 1)[-1]
    import shutil
    shutil.rmtree(target)
    removed = [str(target)]
    reports_root = ROOT / "reports"
    for item in reports_root.rglob(f"*{stamp}*"):
        if item.is_file() and reports_root.resolve() in item.resolve().parents:
            item.unlink()
            removed.append(str(item))
    if delete_build:
        build = (ROOT / "build_artifacts" / "telemetry_validation").resolve()
        if build.is_dir() and ROOT.resolve() in build.parents:
            shutil.rmtree(build)
            removed.append(str(build))
    with lock:
        state.update({"capture": "", "condition": "", "duration": 0, "started": None, "capture_started": None, "log": []})
    return removed


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        return

    def send_json(self, value, code=200):
        body = json.dumps(value).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/status":
            with lock:
                process = state["process"]
                running = process is not None and process.poll() is None
                flash_process = state["flash_process"]
                flashing = flash_process is not None and flash_process.poll() is None
                capture_started = state["capture_started"]
                elapsed = time.time() - capture_started if running and capture_started else 0
                summary = state["summary"]
                if not running and summary is None:
                    latest = latest_capture_dir()
                    summary = summarize_capture(latest) if latest else None
                    state["summary"] = summary
                response = {"running": running, "flashing": flashing, "operation": state["operation"],
                            "armed": running and capture_started is None,
                            "elapsed_s": elapsed,
                            "remaining_s": max(0, state["duration"] - elapsed) if running and capture_started else 0,
                            "condition": state["condition"], "capture": state["capture"], "log": list(state["log"]),
                            "summary": summary}
            self.send_json(response)
            return
        if path == "/api/serial-ports":
            result = subprocess.run(
                [sys.executable, str(ROOT / "tools" / "list_serial_ports.py")],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
            if result.returncode:
                self.send_json({"ports": [], "error": result.stderr.strip()}, 500)
            else:
                self.send_json(json.loads(result.stdout or '{"ports": []}'))
            return
        if path == "/api/markers":
            try:
                self.send_json(json.loads(MARKERS_PATH.read_text(encoding="utf-8")))
            except FileNotFoundError:
                self.send_json({})
            return
        if path == "/api/datasets":
            self.send_json({"datasets": dataset_listing()})
            return
        if path == "/api/run-metadata":
            try:
                run = parse_qs(parsed.query).get("run", [""])[0]
                self.send_json(run_metadata(run))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if path == "/api/run-summary":
            try:
                run = parse_qs(parsed.query).get("run", [""])[0]
                self.send_json(run_summary(run))
            except Exception as exc:
                self.send_json({"error": str(exc)}, 400)
            return
        if path == "/floorplan.jpg":
            data = (WEB / "floorplan.jpg").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        file = WEB / ("index.html" if path in ("/", "") else path.lstrip("/"))
        if file.is_file() and WEB in file.parents:
            data = file.read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        try:
            if path == "/api/start":
                start_run(payload); self.send_json({"ok": True}); return
            if path == "/api/flash":
                start_flash(payload.get("port", "COM7")); self.send_json({"ok": True}); return
            if path == "/api/datasets":
                name = create_dataset(payload.get("name"))
                self.send_json({"ok": True, "name": name}); return
            if path == "/api/assign-run":
                new_path = assign_run(payload.get("run"), payload.get("dataset"))
                self.send_json({"ok": True, "run": new_path}); return
            if path == "/api/stop":
                with lock:
                    process = state["process"]
                    active = process is not None and process.poll() is None
                    flash_process = state["flash_process"]
                    flashing = flash_process is not None and flash_process.poll() is None
                    if active:
                        process.terminate()
                    if flashing:
                        flash_process.terminate()
                if active or flashing:
                    add_log("Stop requested")
                self.send_json({"ok": True}); return
            if path == "/api/delete-latest":
                removed = delete_latest_run(bool(payload.get("delete_build", False)))
                self.send_json({"ok": True, "removed": removed}); return
            if path == "/api/markers":
                MARKERS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8"); self.send_json({"ok": True}); return
            self.send_error(404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, 400)


if __name__ == "__main__":
    CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
    latest = latest_capture_dir()
    state["summary"] = summarize_capture(latest) if latest else None
    print(f"Field terminal: http://0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
