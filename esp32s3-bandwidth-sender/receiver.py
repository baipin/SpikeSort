import argparse
import base64
import csv
import hashlib
import json
import math
import os
import socket
import sqlite3
import struct
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from pathlib import Path


HOST = "0.0.0.0"
PORT = 5001
WEBSOCKET_HOST = "127.0.0.1"
WEBSOCKET_PORT = 8765
INFLUX_URL = "http://127.0.0.1:8086"
INFLUX_ORG = "neural-link-lab"
INFLUX_BUCKET = "esp32s3_bandwidth"
INFLUX_TOKEN = "bandwidth-monitor-token"
INFLUX_MEASUREMENT = "bandwidth_window"
PAYLOAD_BYTES = 4096
HEADER_BYTES = 12
CRC_BYTES = 2
FRAME_BYTES = HEADER_BYTES + PAYLOAD_BYTES + CRC_BYTES
TARGET_FPS = 20
TARGET_RATE_KIB_S = TARGET_FPS * FRAME_BYTES / 1024.0
STALE_CONNECTION_TIMEOUT_S = 3.0
RECENT_WINDOW_COUNT = 30
MAX_SEQ_JUMP = 10000
MAX_MONOTONIC_SEND_TS_US = 7 * 24 * 60 * 60 * 1_000_000
MIN_EPOCH_SEND_TS_US = 1_600_000_000_000_000
MAX_CLOCK_SKEW_MS = 60_000.0
MAX_RESYNC_BYTES = FRAME_BYTES * 3


def crc16_ccitt_false(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def stddev(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * pct / 100.0
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[int(index)]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def classify_timestamp(send_ts_us: int, recv_time_ns: int):
    if send_ts_us >= MIN_EPOCH_SEND_TS_US:
        latency_ms = (recv_time_ns - send_ts_us * 1000) / 1_000_000.0
        if -MAX_CLOCK_SKEW_MS <= latency_ms <= MAX_CLOCK_SKEW_MS:
            return "epoch_us", latency_ms
        return "epoch_untrusted", None
    return "monotonic_us", None


class WebSocketBroadcaster:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.clients = set()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._serve, name="metrics_ws", daemon=True)

    def start(self):
        self.thread.start()

    def broadcast_json(self, message):
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        frame = self._encode_text_frame(payload)

        with self.lock:
            clients = list(self.clients)

        for client in clients:
            try:
                client.sendall(frame)
            except OSError:
                self._drop_client(client)

    def _serve(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((self.host, self.port))
            server.listen(8)
            print(f"Metrics WebSocket listening on ws://{self.host}:{self.port}", flush=True)

            while True:
                conn, _addr = server.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn):
        try:
            request = conn.recv(4096).decode("utf-8", errors="replace")
            headers = self._parse_headers(request)
            key = headers.get("sec-websocket-key")
            if not key:
                conn.close()
                return

            accept_key = base64.b64encode(
                hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
            ).decode("ascii")
            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n"
                "\r\n"
            )
            conn.sendall(response.encode("ascii"))
            with self.lock:
                self.clients.add(conn)

            while True:
                if not conn.recv(2):
                    break
        except OSError:
            pass
        finally:
            self._drop_client(conn)

    def _drop_client(self, conn):
        with self.lock:
            self.clients.discard(conn)
        try:
            conn.close()
        except OSError:
            pass

    @staticmethod
    def _parse_headers(request: str):
        headers = {}
        for line in request.split("\r\n")[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()
        return headers

    @staticmethod
    def _encode_text_frame(payload: bytes):
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(length)
        elif length <= 0xFFFF:
            header.extend([126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(127)
            header.extend(length.to_bytes(8, "big"))
        return bytes(header) + payload


class CaptureStore:
    def __init__(self, output_dir: Path, run_metadata=None):
        output_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_metadata = run_metadata or {}
        self.run_id = self.run_metadata.get("experiment_id") or started_at
        self.frame_csv_path = output_dir / f"frames_{started_at}.csv"
        self.metrics_csv_path = output_dir / f"metrics_{started_at}.csv"
        self.sqlite_path = output_dir / "bandwidth_capture.sqlite3"
        self.frame_csv_file = self.frame_csv_path.open("w", newline="", encoding="utf-8")
        self.metrics_csv_file = self.metrics_csv_path.open("w", newline="", encoding="utf-8")
        self.frame_writer = csv.DictWriter(
            self.frame_csv_file,
            fieldnames=[
                "recv_time_ns",
                "seq",
                "send_ts_us",
                "timestamp_mode",
                "latency_ms",
                "payload_bytes",
                "frame_bytes",
                "arrival_interval_ms",
            ],
        )
        self.metrics_writer = csv.DictWriter(
            self.metrics_csv_file,
            fieldnames=[
                "window_end_ns",
                "elapsed_s",
                "fps",
                "rate_kib_s",
                "missing_frames",
                "loss_rate",
                "crc_errors",
                "old_frames",
                "avg_interval_ms",
                "interval_jitter_ms",
                "bandwidth_jitter_kib_s",
                "latency_count",
                "latency_avg_ms",
                "latency_p50_ms",
                "latency_p95_ms",
                "latency_p99_ms",
            ],
            extrasaction="ignore",
        )
        self.frame_writer.writeheader()
        self.metrics_writer.writeheader()
        self.db = sqlite3.connect(self.sqlite_path)
        self._init_db()

    def close(self):
        self.frame_csv_file.close()
        self.metrics_csv_file.close()
        self.db.close()

    def record_frame(self, row):
        self.frame_writer.writerow(row)
        self.db.execute(
            """
            INSERT INTO frames
            (recv_time_ns, seq, send_ts_us, timestamp_mode, latency_ms, payload_bytes, frame_bytes, arrival_interval_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["recv_time_ns"],
                row["seq"],
                row["send_ts_us"],
                row["timestamp_mode"],
                row["latency_ms"],
                row["payload_bytes"],
                row["frame_bytes"],
                row["arrival_interval_ms"],
            ),
        )

    def record_metrics(self, row):
        self.metrics_writer.writerow(row)
        self.frame_csv_file.flush()
        self.metrics_csv_file.flush()
        self.db.execute(
            """
            INSERT INTO metrics
            (window_end_ns, elapsed_s, fps, rate_kib_s, missing_frames, loss_rate,
             crc_errors, old_frames, avg_interval_ms, interval_jitter_ms, bandwidth_jitter_kib_s,
             latency_count, latency_avg_ms, latency_p50_ms, latency_p95_ms, latency_p99_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["window_end_ns"],
                row["elapsed_s"],
                row["fps"],
                row["rate_kib_s"],
                row["missing_frames"],
                row["loss_rate"],
                row["crc_errors"],
                row["old_frames"],
                row["avg_interval_ms"],
                row["interval_jitter_ms"],
                row["bandwidth_jitter_kib_s"],
                row["latency_count"],
                row["latency_avg_ms"],
                row["latency_p50_ms"],
                row["latency_p95_ms"],
                row["latency_p99_ms"],
            ),
        )
        self.db.commit()

    def _init_db(self):
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS experiment_runs (
                run_id TEXT PRIMARY KEY,
                started_at_ns INTEGER NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recv_time_ns INTEGER NOT NULL,
                seq INTEGER NOT NULL,
                send_ts_us INTEGER NOT NULL,
                timestamp_mode TEXT NOT NULL DEFAULT 'monotonic_us',
                latency_ms REAL,
                payload_bytes INTEGER NOT NULL,
                frame_bytes INTEGER NOT NULL,
                arrival_interval_ms REAL
            )
            """
        )
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                window_end_ns INTEGER NOT NULL,
                elapsed_s REAL NOT NULL,
                fps REAL NOT NULL,
                rate_kib_s REAL NOT NULL,
                missing_frames INTEGER NOT NULL,
                loss_rate REAL NOT NULL,
                crc_errors INTEGER NOT NULL,
                old_frames INTEGER NOT NULL,
                avg_interval_ms REAL NOT NULL,
                interval_jitter_ms REAL NOT NULL,
                bandwidth_jitter_kib_s REAL NOT NULL,
                latency_count INTEGER NOT NULL DEFAULT 0,
                latency_avg_ms REAL,
                latency_p50_ms REAL,
                latency_p95_ms REAL,
                latency_p99_ms REAL
            )
            """
        )
        self._ensure_column("frames", "timestamp_mode", "TEXT NOT NULL DEFAULT 'monotonic_us'")
        self._ensure_column("frames", "latency_ms", "REAL")
        self._ensure_column("metrics", "latency_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("metrics", "latency_avg_ms", "REAL")
        self._ensure_column("metrics", "latency_p50_ms", "REAL")
        self._ensure_column("metrics", "latency_p95_ms", "REAL")
        self._ensure_column("metrics", "latency_p99_ms", "REAL")
        self.db.execute(
            """
            INSERT OR REPLACE INTO experiment_runs
            (run_id, started_at_ns, metadata_json)
            VALUES (?, ?, ?)
            """,
            (
                self.run_id,
                time.time_ns(),
                json.dumps(self.run_metadata, separators=(",", ":"), sort_keys=True),
            ),
        )
        self.db.commit()

    def _ensure_column(self, table, column, definition):
        columns = {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


class InfluxWriter:
    def __init__(
        self,
        url: str,
        org: str,
        bucket: str,
        token: str,
        measurement: str,
        enabled: bool,
        extra_tags=None,
    ):
        self.url = url.rstrip("/")
        self.org = org
        self.bucket = bucket
        self.token = token
        self.measurement = measurement
        self.enabled = enabled
        self.extra_tags = extra_tags or {}
        self.failed_writes = 0
        self.last_error = None

    def write_metrics(self, metrics):
        if not self.enabled:
            return

        line = self._line_protocol(metrics)
        endpoint = f"{self.url}/api/v2/write?org={self.org}&bucket={self.bucket}&precision=ns"
        request = urllib.request.Request(
            endpoint,
            data=line.encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=0.5) as response:
                response.read()
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            self.failed_writes += 1
            self.last_error = str(exc)
            if self.failed_writes == 1 or self.failed_writes % 30 == 0:
                print(f"InfluxDB write failed ({self.failed_writes}): {self.last_error}", flush=True)

    def _line_protocol(self, metrics):
        tags = {
            "device": "esp32s3",
            "transport": "wifi_tcp",
            "workload": "spike_stream_surrogate",
            "payload_bytes": str(PAYLOAD_BYTES),
            "frame_bytes": str(FRAME_BYTES),
        }
        for key, value in self.extra_tags.items():
            if value not in (None, ""):
                tags[key] = str(value)
        fields = {
            "fps": metrics["fps"],
            "target_fps": TARGET_FPS,
            "rate_kib_s": metrics["rate_kib_s"],
            "target_rate_kib_s": TARGET_RATE_KIB_S,
            "missing_frames": metrics["missing_frames"],
            "loss_rate": metrics["loss_rate"],
            "crc_errors": metrics["crc_errors"],
            "old_frames": metrics["old_frames"],
            "avg_interval_ms": metrics["avg_interval_ms"],
            "interval_jitter_ms": metrics["interval_jitter_ms"],
            "bandwidth_jitter_kib_s": metrics["bandwidth_jitter_kib_s"],
            "latency_count": metrics["latency_count"],
        }
        for key in ("latency_avg_ms", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"):
            if metrics[key] is not None:
                fields[key] = metrics[key]
        tag_text = ",".join(f"{self._escape_tag(key)}={self._escape_tag(value)}" for key, value in tags.items())
        field_text = ",".join(f"{self._escape_field_key(key)}={self._format_field(value)}" for key, value in fields.items())
        return f"{self._escape_measurement(self.measurement)},{tag_text} {field_text} {metrics['window_end_ns']}"

    @staticmethod
    def _escape_measurement(value):
        return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,")

    @staticmethod
    def _escape_tag(value):
        return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

    @staticmethod
    def _escape_field_key(value):
        return str(value).replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

    @staticmethod
    def _format_field(value):
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return f"{value}i"
        return repr(float(value))


class WindowStats:
    def __init__(self):
        self.expected_seq = None
        self.frames = 0
        self.window_bytes = 0
        self.missing_frames = 0
        self.crc_errors = 0
        self.old_frames = 0
        self.last_recv_time_ns = None
        self.intervals_ms = []
        self.latencies_ms = []
        self.window_start = time.monotonic()
        self.recent_rates = deque(maxlen=RECENT_WINDOW_COUNT)

    def record_crc_error(self):
        self.crc_errors += 1

    def looks_plausible(self, seq: int, send_ts_us: int):
        if send_ts_us < 0:
            return False
        if send_ts_us >= MIN_EPOCH_SEND_TS_US:
            return True
        if send_ts_us > MAX_MONOTONIC_SEND_TS_US:
            return False
        if self.expected_seq is not None and seq > self.expected_seq + MAX_SEQ_JUMP:
            return False
        return True

    def record_frame(self, seq: int, recv_time_ns: int, latency_ms):
        interval_ms = None
        if self.last_recv_time_ns is not None:
            interval_ms = (recv_time_ns - self.last_recv_time_ns) / 1_000_000.0
            self.intervals_ms.append(interval_ms)
        self.last_recv_time_ns = recv_time_ns
        if latency_ms is not None:
            self.latencies_ms.append(latency_ms)

        if self.expected_seq is None:
            self.expected_seq = seq + 1
        elif seq == self.expected_seq:
            self.expected_seq += 1
        elif seq > self.expected_seq:
            self.missing_frames += seq - self.expected_seq
            self.expected_seq = seq + 1
        else:
            self.old_frames += 1

        self.frames += 1
        self.window_bytes += FRAME_BYTES
        return interval_ms

    def maybe_emit_metrics(self):
        now = time.monotonic()
        elapsed = now - self.window_start
        if elapsed < 1.0:
            return None

        expected_frames = self.frames + self.missing_frames
        rate_kib_s = self.window_bytes / elapsed / 1024.0
        self.recent_rates.append(rate_kib_s)
        latency_count = len(self.latencies_ms)
        metrics = {
            "type": "metrics",
            "window_end_ns": time.time_ns(),
            "elapsed_s": elapsed,
            "fps": self.frames / elapsed,
            "rate_kib_s": rate_kib_s,
            "missing_frames": self.missing_frames,
            "loss_rate": self.missing_frames / expected_frames if expected_frames else 0.0,
            "crc_errors": self.crc_errors,
            "old_frames": self.old_frames,
            "avg_interval_ms": sum(self.intervals_ms) / len(self.intervals_ms) if self.intervals_ms else 0.0,
            "interval_jitter_ms": stddev(self.intervals_ms),
            "bandwidth_jitter_kib_s": stddev(list(self.recent_rates)),
            "latency_count": latency_count,
            "latency_avg_ms": sum(self.latencies_ms) / latency_count if latency_count else None,
            "latency_p50_ms": percentile(self.latencies_ms, 50) if latency_count else None,
            "latency_p95_ms": percentile(self.latencies_ms, 95) if latency_count else None,
            "latency_p99_ms": percentile(self.latencies_ms, 99) if latency_count else None,
        }

        self.frames = 0
        self.window_bytes = 0
        self.missing_frames = 0
        self.crc_errors = 0
        self.old_frames = 0
        self.intervals_ms = []
        self.latencies_ms = []
        self.window_start = now
        return metrics


def parse_args():
    parser = argparse.ArgumentParser(description="ESP32-S3 bandwidth frame receiver")
    parser.add_argument("--host", default=os.environ.get("BANDWIDTH_RECEIVER_HOST", HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BANDWIDTH_RECEIVER_PORT", PORT)))
    parser.add_argument("--output-dir", default=os.environ.get("BANDWIDTH_OUTPUT_DIR", "captures"))
    parser.add_argument("--ws-host", default=os.environ.get("BANDWIDTH_WS_HOST", WEBSOCKET_HOST))
    parser.add_argument("--ws-port", type=int, default=int(os.environ.get("BANDWIDTH_WS_PORT", WEBSOCKET_PORT)))
    parser.add_argument("--no-websocket", action="store_true")
    parser.add_argument("--influx-url", default=os.environ.get("INFLUX_URL", INFLUX_URL))
    parser.add_argument("--influx-org", default=os.environ.get("INFLUX_ORG", INFLUX_ORG))
    parser.add_argument("--influx-bucket", default=os.environ.get("INFLUX_BUCKET", INFLUX_BUCKET))
    parser.add_argument("--influx-token", default=os.environ.get("INFLUX_TOKEN", INFLUX_TOKEN))
    parser.add_argument("--influx-measurement", default=os.environ.get("INFLUX_MEASUREMENT", INFLUX_MEASUREMENT))
    parser.add_argument("--no-influx", action="store_true")
    parser.add_argument("--experiment-id", default=os.environ.get("BANDWIDTH_EXPERIMENT_ID"))
    parser.add_argument("--condition", default=os.environ.get("BANDWIDTH_CONDITION"))
    parser.add_argument("--notes", default=os.environ.get("BANDWIDTH_NOTES"))
    parser.add_argument("--manifest", help="Optional experiment JSON manifest to bind to this capture run")
    parser.add_argument(
        "--read-limit-kib-s",
        type=float,
        default=float(os.environ.get("BANDWIDTH_READ_LIMIT_KIB_S", "0")),
        help="Throttle receiver socket reads to this KiB/s. Use 0 for no artificial limit.",
    )
    return parser.parse_args()


def load_run_metadata(args):
    metadata = {}
    if args.manifest:
        with Path(args.manifest).open("r", encoding="utf-8") as handle:
            metadata.update(json.load(handle))
    if args.experiment_id:
        metadata["experiment_id"] = args.experiment_id
    if args.condition:
        metadata["condition_label"] = args.condition
    if args.notes:
        metadata["operator_notes"] = args.notes
    if args.read_limit_kib_s > 0:
        metadata["read_limit_kib_s"] = args.read_limit_kib_s
    metadata.setdefault("receiver_started_at_local", datetime.now().isoformat(timespec="seconds"))
    return metadata


def run_receiver(args, store: CaptureStore, broadcaster, influx_writer: InfluxWriter):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(1)
        print(
            f"Listening on {args.host}:{args.port}, frame={FRAME_BYTES} bytes, payload={PAYLOAD_BYTES} bytes",
            flush=True,
        )
        print(f"CSV output: {store.frame_csv_path} and {store.metrics_csv_path}", flush=True)
        print(f"SQLite output: {store.sqlite_path}", flush=True)
        if influx_writer.enabled:
            print(
                f"InfluxDB output: {args.influx_url} org={args.influx_org} bucket={args.influx_bucket}",
                flush=True,
            )
        read_limit_bytes_s = args.read_limit_kib_s * 1024.0 if args.read_limit_kib_s > 0 else 0.0
        if read_limit_bytes_s > 0:
            print(f"Artificial receiver read limit: {args.read_limit_kib_s:.1f} KiB/s", flush=True)

        while True:
            conn, addr = server.accept()
            with conn:
                conn.settimeout(STALE_CONNECTION_TIMEOUT_S)
                print(f"Connected by {addr}", flush=True)
                buffer = bytearray()
                stats = WindowStats()
                invalid_scan_bytes = 0
                close_connection = False
                read_deadline = time.monotonic()

                while True:
                    try:
                        data = conn.recv(65536)
                    except socket.timeout:
                        print("No data for 3 seconds; closing stale connection", flush=True)
                        break

                    if not data:
                        print("Disconnected", flush=True)
                        break

                    if read_limit_bytes_s > 0:
                        read_deadline = max(read_deadline, time.monotonic()) + len(data) / read_limit_bytes_s
                        sleep_s = read_deadline - time.monotonic()
                        if sleep_s > 0:
                            time.sleep(sleep_s)

                    buffer.extend(data)

                    while len(buffer) >= FRAME_BYTES:
                        recv_crc = struct.unpack_from("<H", buffer, HEADER_BYTES + PAYLOAD_BYTES)[0]
                        calc_crc = crc16_ccitt_false(buffer[: HEADER_BYTES + PAYLOAD_BYTES])
                        if calc_crc != recv_crc:
                            stats.record_crc_error()
                            del buffer[0]
                            invalid_scan_bytes += 1
                            if invalid_scan_bytes >= MAX_RESYNC_BYTES:
                                print("Unable to resync frame stream; reconnecting", flush=True)
                                close_connection = True
                                break
                            continue

                        seq, send_ts_us = struct.unpack_from("<IQ", buffer, 0)
                        if not stats.looks_plausible(seq, send_ts_us):
                            stats.record_crc_error()
                            del buffer[0]
                            invalid_scan_bytes += 1
                            if invalid_scan_bytes >= MAX_RESYNC_BYTES:
                                print("Unable to resync plausible frame stream; reconnecting", flush=True)
                                close_connection = True
                                break
                            continue

                        del buffer[:FRAME_BYTES]
                        invalid_scan_bytes = 0
                        recv_time_ns = time.time_ns()
                        timestamp_mode, latency_ms = classify_timestamp(send_ts_us, recv_time_ns)
                        arrival_interval_ms = stats.record_frame(seq, recv_time_ns, latency_ms)
                        store.record_frame(
                            {
                                "recv_time_ns": recv_time_ns,
                                "seq": seq,
                                "send_ts_us": send_ts_us,
                                "timestamp_mode": timestamp_mode,
                                "latency_ms": latency_ms,
                                "payload_bytes": PAYLOAD_BYTES,
                                "frame_bytes": FRAME_BYTES,
                                "arrival_interval_ms": arrival_interval_ms,
                            }
                        )

                    metrics = stats.maybe_emit_metrics()
                    if metrics is not None:
                        store.record_metrics(metrics)
                        influx_writer.write_metrics(metrics)
                        if broadcaster is not None:
                            broadcaster.broadcast_json(metrics)
                        print(
                            "fps={fps:.1f} rate={rate:.1f} KiB/s missing={missing} "
                            "loss={loss:.3%} crc_errors={crc} old={old} "
                            "avg_interval={avg:.2f} ms jitter={jitter:.2f} ms "
                            "bw_jitter={bw_jitter:.2f} KiB/s latency_p95={latency_p95}".format(
                                fps=metrics["fps"],
                                rate=metrics["rate_kib_s"],
                                missing=metrics["missing_frames"],
                                loss=metrics["loss_rate"],
                                crc=metrics["crc_errors"],
                                old=metrics["old_frames"],
                                avg=metrics["avg_interval_ms"],
                                jitter=metrics["interval_jitter_ms"],
                                bw_jitter=metrics["bandwidth_jitter_kib_s"],
                                latency_p95=(
                                    f"{metrics['latency_p95_ms']:.2f} ms"
                                    if metrics["latency_p95_ms"] is not None
                                    else "unavailable"
                                ),
                            ),
                            flush=True,
                        )

                    if close_connection:
                        break


def main():
    args = parse_args()
    run_metadata = load_run_metadata(args)
    store = CaptureStore(Path(args.output_dir), run_metadata)
    broadcaster = None
    if not args.no_websocket:
        broadcaster = WebSocketBroadcaster(args.ws_host, args.ws_port)
        broadcaster.start()
    influx_writer = InfluxWriter(
        args.influx_url,
        args.influx_org,
        args.influx_bucket,
        args.influx_token,
        args.influx_measurement,
        not args.no_influx,
        {
            "experiment_id": run_metadata.get("experiment_id"),
            "condition": run_metadata.get("condition_label"),
            "read_limit_kib_s": run_metadata.get("read_limit_kib_s"),
        },
    )

    try:
        run_receiver(args, store, broadcaster, influx_writer)
    finally:
        store.close()


if __name__ == "__main__":
    main()
