import argparse
import ctypes
import json
import os
import socket
import struct
import time
from datetime import datetime
from pathlib import Path

import receiver as rx


DEFAULT_PAYLOAD_BYTES = 4096
DEFAULT_TARGET_FPS = 20
DEFAULT_SOCKET_RCVBUF = 4 * 1024 * 1024


def parse_args():
    parser = argparse.ArgumentParser(description="ESP32-S3 UDP packet-loss and throughput receiver")
    parser.add_argument("--host", default=os.environ.get("BANDWIDTH_RECEIVER_HOST", rx.HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("BANDWIDTH_RECEIVER_PORT", rx.PORT)))
    parser.add_argument("--output-dir", default=os.environ.get("BANDWIDTH_OUTPUT_DIR", "captures"))
    parser.add_argument("--payload-bytes", type=int, default=int(os.environ.get("BANDWIDTH_PAYLOAD_BYTES", DEFAULT_PAYLOAD_BYTES)))
    parser.add_argument("--target-fps", type=int, default=int(os.environ.get("BANDWIDTH_TARGET_FPS", DEFAULT_TARGET_FPS)))
    parser.add_argument("--skip-crc", action="store_true", help="Diagnostic mode: accept frames without CRC validation.")
    parser.add_argument("--socket-rcvbuf", type=int, default=int(os.environ.get("BANDWIDTH_UDP_RCVBUF", DEFAULT_SOCKET_RCVBUF)))
    parser.add_argument("--source-warmup-s", type=float, default=1.0, help="Discard UDP datagrams for this many seconds after bind to drain stale OS queues.")
    parser.add_argument(
        "--arm-delay-s",
        type=float,
        default=0.0,
        help="After bind and warmup, keep draining packets for this many seconds before accepting the first source. Useful when the operator must reset a detached board after the receiver is already listening.",
    )
    parser.add_argument("--allow-source-port-changes", action="store_true", help="Accept UDP datagrams from changing source ports during one capture.")
    parser.add_argument(
        "--abort-on-source-port-change",
        action="store_true",
        help="Abort the capture if the accepted ESP32 UDP source port changes. Use for formal detached field traces.",
    )
    parser.add_argument("--ws-host", default=os.environ.get("BANDWIDTH_WS_HOST", rx.WEBSOCKET_HOST))
    parser.add_argument("--ws-port", type=int, default=int(os.environ.get("BANDWIDTH_WS_PORT", rx.WEBSOCKET_PORT)))
    parser.add_argument("--no-websocket", action="store_true")
    parser.add_argument("--influx-url", default=os.environ.get("INFLUX_URL", rx.INFLUX_URL))
    parser.add_argument("--influx-org", default=os.environ.get("INFLUX_ORG", rx.INFLUX_ORG))
    parser.add_argument("--influx-bucket", default=os.environ.get("INFLUX_BUCKET", rx.INFLUX_BUCKET))
    parser.add_argument("--influx-token", default=os.environ.get("INFLUX_TOKEN", rx.INFLUX_TOKEN))
    parser.add_argument("--influx-measurement", default=os.environ.get("INFLUX_MEASUREMENT", rx.INFLUX_MEASUREMENT))
    parser.add_argument("--no-influx", action="store_true")
    parser.add_argument("--experiment-id", default=os.environ.get("BANDWIDTH_EXPERIMENT_ID"))
    parser.add_argument("--condition", default=os.environ.get("BANDWIDTH_CONDITION"))
    parser.add_argument("--notes", default=os.environ.get("BANDWIDTH_NOTES"))
    parser.add_argument("--manifest", help="Optional experiment JSON manifest to bind to this capture run")
    parser.add_argument(
        "--require-epoch-timestamps",
        action="store_true",
        help="Abort if received frames do not carry trusted Unix epoch timestamps for latency analysis.",
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        help="Optional capture duration in seconds. The receiver exits cleanly after this many seconds.",
    )
    parser.add_argument(
        "--startup-timeout-s",
        type=float,
        default=30.0,
        help="Abort if no valid UDP frame arrives within this many seconds after bind.",
    )
    parser.add_argument(
        "--defer-frame-storage",
        action="store_true",
        help="Keep per-packet records in memory during capture and write CSV/SQLite after capture stops.",
    )
    parser.add_argument(
        "--high-priority",
        action="store_true",
        help="On Windows, request high process priority to reduce receiver scheduling stalls during diagnostics.",
    )
    return parser.parse_args()


def request_high_priority():
    """Best-effort Windows scheduling hint; failure must not affect captures."""
    if os.name != "nt":
        return
    high_priority_class = 0x00000080
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        kernel32.SetPriorityClass.restype = ctypes.c_int
        process = kernel32.GetCurrentProcess()
        if not kernel32.SetPriorityClass(process, high_priority_class):
            raise ctypes.WinError(ctypes.get_last_error())
        print("Receiver process priority set to HIGH", flush=True)
    except OSError as exc:
        print(f"Warning: unable to set receiver priority: {exc}", flush=True)


def configure_receiver_globals(args):
    rx.PAYLOAD_BYTES = args.payload_bytes
    rx.FRAME_BYTES = rx.HEADER_BYTES + args.payload_bytes + rx.CRC_BYTES
    rx.TARGET_FPS = args.target_fps
    rx.TARGET_RATE_KIB_S = args.target_fps * rx.FRAME_BYTES / 1024.0
    rx.MAX_RESYNC_BYTES = rx.FRAME_BYTES * 3


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
    metadata["transport"] = "udp"
    metadata["payload_bytes"] = args.payload_bytes
    metadata["frame_bytes"] = rx.FRAME_BYTES
    metadata["target_fps"] = args.target_fps
    stream = metadata.get("stream")
    if isinstance(stream, dict):
        stream["target_fps"] = args.target_fps
        stream["payload_bytes"] = args.payload_bytes
        stream["frame_bytes"] = rx.FRAME_BYTES
        stream["nominal_rate_kib_s"] = rx.TARGET_RATE_KIB_S
        stream["pacing"] = "configured"
    metadata["udp_socket_rcvbuf"] = args.socket_rcvbuf
    metadata.setdefault("receiver_started_at_local", datetime.now().isoformat(timespec="seconds"))
    return metadata


def run_udp_receiver(args, store, broadcaster, influx_writer):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if args.socket_rcvbuf > 0:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, args.socket_rcvbuf)
        sock.settimeout(0.25)
        sock.bind((args.host, args.port))
        actual_rcvbuf = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        print(
            f"Listening for UDP on {args.host}:{args.port}, frame={rx.FRAME_BYTES} bytes, "
            f"payload={rx.PAYLOAD_BYTES} bytes, target_fps={rx.TARGET_FPS}",
            flush=True,
        )
        print(f"UDP SO_RCVBUF requested={args.socket_rcvbuf} actual={actual_rcvbuf}", flush=True)
        print(f"CSV output: {store.frame_csv_path} and {store.metrics_csv_path}", flush=True)
        print(f"SQLite output: {store.sqlite_path}", flush=True)
        if influx_writer.enabled:
            print(
                f"InfluxDB output: {args.influx_url} org={args.influx_org} bucket={args.influx_bucket}",
                flush=True,
            )

        if args.source_warmup_s > 0:
            warmup_deadline = time.monotonic() + args.source_warmup_s
            drained = 0
            while time.monotonic() < warmup_deadline:
                try:
                    sock.recvfrom(max(65535, rx.FRAME_BYTES + 64))
                    drained += 1
                except socket.timeout:
                    continue
            if drained:
                print(f"Drained {drained} stale UDP datagrams before capture start", flush=True)

        if args.arm_delay_s > 0:
            arm_deadline = time.monotonic() + args.arm_delay_s
            drained = 0
            print(
                f"Arming receiver for {args.arm_delay_s:.1f} s; reset/power-cycle the detached ESP32 now.",
                flush=True,
            )
            while time.monotonic() < arm_deadline:
                try:
                    sock.recvfrom(max(65535, rx.FRAME_BYTES + 64))
                    drained += 1
                except socket.timeout:
                    continue
            print(f"Arming window done; drained {drained} UDP datagrams and will accept the next source.", flush=True)

        stats = rx.WindowStats()
        accepted_addr = None
        ignored_sources = {}
        accepted_additional_sources = {}
        capture_start = None
        capture_announced = False
        last_valid_packet_time = None
        last_idle_log_time = 0.0
        startup_deadline = time.monotonic() + args.startup_timeout_s if args.startup_timeout_s is not None else None
        while True:
            if capture_start is None and startup_deadline is not None and time.monotonic() >= startup_deadline:
                raise SystemExit(
                    f"No valid UDP frame received within {args.startup_timeout_s:.1f} s after bind; "
                    "check the board power/reset and WiFi association before retrying."
                )
            if args.duration_s is not None and capture_start is not None:
                if time.monotonic() - capture_start >= args.duration_s:
                    print(f"Reached requested UDP capture duration: {args.duration_s:.1f} s", flush=True)
                    return
            try:
                data, addr = sock.recvfrom(max(65535, rx.FRAME_BYTES + 64))
            except socket.timeout:
                if capture_start is not None and last_valid_packet_time is not None:
                    now = time.monotonic()
                    idle_s = now - last_valid_packet_time
                    if idle_s >= 5.0 and now - last_idle_log_time >= 5.0:
                        print(f"UDP_IDLE no valid packet received for {idle_s:.1f} s", flush=True)
                        last_idle_log_time = now
                continue
            source_change_candidate = False
            if accepted_addr is None:
                accepted_addr = addr
                print(f"Receiving UDP packets from {addr}", flush=True)
            if addr != accepted_addr and not args.allow_source_port_changes:
                if args.abort_on_source_port_change and addr[0] == accepted_addr[0]:
                    source_change_candidate = True
                else:
                    ignored_sources[addr] = ignored_sources.get(addr, 0) + 1
                    if ignored_sources[addr] in (1, 10, 100, 1000):
                        print(f"Ignoring UDP packets from stale source {addr} count={ignored_sources[addr]}", flush=True)
                    continue
            elif addr != accepted_addr:
                source_change_candidate = True

            if addr != accepted_addr and not source_change_candidate:
                ignored_sources[addr] = ignored_sources.get(addr, 0) + 1
                if ignored_sources[addr] in (1, 10, 100, 1000):
                    print(f"Ignoring UDP packets from stale source {addr} count={ignored_sources[addr]}", flush=True)
                continue

            recv_time_ns = time.time_ns()
            if len(data) != rx.FRAME_BYTES:
                stats.record_crc_error()
            else:
                crc_ok = True
                if not args.skip_crc:
                    recv_crc = struct.unpack_from("<H", data, rx.HEADER_BYTES + rx.PAYLOAD_BYTES)[0]
                    calc_crc = rx.crc16_ccitt_false(data[: rx.HEADER_BYTES + rx.PAYLOAD_BYTES])
                    crc_ok = calc_crc == recv_crc
                if not crc_ok:
                    stats.record_crc_error()
                else:
                    seq, send_ts_us = struct.unpack_from("<IQ", data, 0)
                    if not stats.looks_plausible(seq, send_ts_us):
                        stats.record_crc_error()
                    else:
                        if source_change_candidate and addr != accepted_addr:
                            if stats.expected_seq is not None and seq < stats.expected_seq:
                                ignored_sources[addr] = ignored_sources.get(addr, 0) + 1
                                if ignored_sources[addr] in (1, 10, 100, 1000):
                                    print(
                                        f"Ignoring old UDP source {addr} seq={seq} "
                                        f"expected>={stats.expected_seq} count={ignored_sources[addr]}",
                                        flush=True,
                                    )
                                continue
                            if args.abort_on_source_port_change:
                                raise SystemExit(
                                    "UDP source port changed during a strict capture with a forward sequence number: "
                                    f"previous={accepted_addr}, new={addr}, seq={seq}. "
                                    "Discard this run and reset/restart the ESP32 before retrying."
                                )
                            accepted_additional_sources[addr] = accepted_additional_sources.get(addr, 0) + 1
                            if accepted_additional_sources[addr] in (1, 10, 100, 1000):
                                print(
                                    f"Switching/accepting UDP source {addr} seq={seq} "
                                    f"previous={accepted_addr} count={accepted_additional_sources[addr]}",
                                    flush=True,
                                )
                            accepted_addr = addr
                            # A source-port change denotes a new ESP32 UDP stream.
                            # Do not turn the new stream's origin into artificial loss.
                            stats.reset_sequence_tracking()
                            print(f"Reset sequence tracking for new UDP source {addr}", flush=True)
                        timestamp_mode, latency_ms = rx.classify_timestamp(send_ts_us, recv_time_ns)
                        sender_diagnostics = None
                        if len(data) >= rx.HEADER_BYTES + 20:
                            sender_diagnostics = rx.parse_sender_telemetry(data[rx.HEADER_BYTES:])
                            if sender_diagnostics is not None:
                                store.record_sender_telemetry(
                                    recv_time_ns,
                                    sender_diagnostics["telemetry_window"],
                                    sender_diagnostics["telemetry_offered_frames"],
                                    sender_diagnostics["telemetry_sent_frames"],
                                    sender_diagnostics["telemetry_dropped_frames"],
                                    sender_diagnostics,
                                )
                        if args.require_epoch_timestamps and timestamp_mode != "epoch_us":
                            raise RuntimeError(
                                "Received UDP frame without a trusted epoch timestamp "
                                f"(seq={seq}, timestamp_mode={timestamp_mode}). "
                                "Check ESP32 SNTP synchronization before running a formal latency test."
                            )
                        arrival_interval_ms, relative_latency_ms = stats.record_frame(seq, recv_time_ns, send_ts_us, latency_ms)
                        if capture_start is None:
                            # Begin the requested duration only after accepting a valid
                            # frame from the selected UDP source, not any datagram.
                            capture_start = time.monotonic()
                        last_valid_packet_time = time.monotonic()
                        store.record_frame(
                            {
                                "recv_time_ns": recv_time_ns,
                                "seq": seq,
                                "send_ts_us": send_ts_us,
                                "timestamp_mode": timestamp_mode,
                                "latency_ms": latency_ms,
                                "relative_latency_ms": relative_latency_ms,
                                "payload_bytes": rx.PAYLOAD_BYTES,
                                "frame_bytes": rx.FRAME_BYTES,
                                "arrival_interval_ms": arrival_interval_ms,
                                "sender_diagnostics": sender_diagnostics or {},
                            }
                        )
                        if not capture_announced:
                            capture_announced = True
                            print("CAPTURE_STARTED first_valid_udp_frame", flush=True)

            metrics = stats.maybe_emit_metrics()
            if metrics is not None:
                store.record_metrics(metrics)
                influx_writer.write_metrics(metrics)
                if broadcaster is not None:
                    broadcaster.broadcast_json(metrics)
                print(
                    "udp fps={fps:.1f} rate={rate:.1f} KiB/s missing={missing} "
                    "loss={loss:.3%} crc_errors={crc} old={old} "
                    "avg_interval={avg:.2f} ms jitter={jitter:.2f} ms "
                    "latency_p95={latency_p95}".format(
                        fps=metrics["fps"],
                        rate=metrics["rate_kib_s"],
                        missing=metrics["missing_frames"],
                        loss=metrics["loss_rate"],
                        crc=metrics["crc_errors"],
                        old=metrics["old_frames"],
                        avg=metrics["avg_interval_ms"],
                        jitter=metrics["interval_jitter_ms"],
                        latency_p95=(
                            f"{metrics['latency_p95_ms']:.2f} ms"
                            if metrics["latency_p95_ms"] is not None
                            else "unavailable"
                        ),
                    ),
                    flush=True,
                )
                if args.duration_s is not None and capture_start is not None:
                    if time.monotonic() - capture_start >= args.duration_s:
                        print(f"Reached requested UDP capture duration: {args.duration_s:.1f} s", flush=True)
                        return


def main():
    args = parse_args()
    if args.high_priority:
        request_high_priority()
    configure_receiver_globals(args)
    run_metadata = load_run_metadata(args)
    store = rx.CaptureStore(Path(args.output_dir), run_metadata, defer_frame_storage=args.defer_frame_storage)
    broadcaster = None
    if not args.no_websocket:
        broadcaster = rx.WebSocketBroadcaster(args.ws_host, args.ws_port)
        broadcaster.start()
    influx_writer = rx.InfluxWriter(
        args.influx_url,
        args.influx_org,
        args.influx_bucket,
        args.influx_token,
        args.influx_measurement,
        not args.no_influx,
        {
            "transport": "wifi_udp",
            "experiment_id": run_metadata.get("experiment_id"),
            "condition": run_metadata.get("condition_label"),
            "payload_bytes": run_metadata.get("payload_bytes"),
            "frame_bytes": run_metadata.get("frame_bytes"),
            "target_fps": run_metadata.get("target_fps"),
        },
    )
    try:
        run_udp_receiver(args, store, broadcaster, influx_writer)
    finally:
        store.close()


if __name__ == "__main__":
    main()
