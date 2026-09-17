import argparse
import csv
import json
import math
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB = Path("captures") / "bandwidth_capture.sqlite3"
TARGET_FPS = 20.0
TARGET_RATE_KIB_S = 20.0 * 4110.0 / 1024.0
MAX_LATENCY_HIST_SAMPLES = 100000


def percentile(values, pct):
    values = sorted(value for value in values if value is not None)
    if not values:
        return None
    index = (len(values) - 1) * pct / 100.0
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[int(index)]
    return values[lower] * (upper - index) + values[upper] * (index - lower)


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def fmt(value, digits=3, suffix=""):
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}{suffix}"


def parse_optional_float(value):
    if value in (None, "", "None", "n/a", "unlimited"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def table_exists(db, table):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def column_names(db, table):
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def load_manifest(path):
    if path is None:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iso_from_ns(value):
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1_000_000_000.0, tz=timezone.utc).isoformat()


def load_latest_db_metadata(db):
    if not table_exists(db, "experiment_runs"):
        return {}
    row = db.execute(
        "SELECT metadata_json FROM experiment_runs ORDER BY started_at_ns DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return {}
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        return {}


def quality_gates(summary):
    gates = []
    target_fps = parse_optional_float(summary.get("target_fps"))
    target_rate_kib_s = parse_optional_float(summary.get("target_rate_kib_s"))

    def add(name, passed, value, criterion):
        gates.append(
            {
                "gate": name,
                "status": "PASS" if passed else "WARN",
                "value": value,
                "criterion": criterion,
            }
        )

    add("CRC / parser integrity", summary["crc_errors_total"] == 0, summary["crc_errors_total"], "crc_errors == 0")
    add("Application loss", (summary["loss_rate_max"] or 0.0) <= 0.001, fmt((summary["loss_rate_max"] or 0.0) * 100, 4, "%"), "max loss <= 0.1%")
    if target_fps is not None:
        add("Mean frame rate", summary["fps_mean"] is not None and summary["fps_mean"] >= target_fps * 0.95, fmt(summary["fps_mean"], 2), "mean fps >= 95% target")
    if target_rate_kib_s is not None:
        add("Mean throughput", summary["rate_kib_s_mean"] is not None and summary["rate_kib_s_mean"] >= target_rate_kib_s * 0.95, fmt(summary["rate_kib_s_mean"], 2, " KiB/s"), "mean throughput >= 95% target")
    latency_available = (summary["latency_count"] > 0) or (summary.get("relative_latency_count") or 0) > 0
    add("Latency availability", latency_available, summary.get("latency_count", 0) or summary.get("relative_latency_count", 0), "Latency samples present")
    return gates


def cutoff_from_db(db, last_minutes):
    if last_minutes is None:
        return None
    max_recv_ns = db.execute("SELECT MAX(recv_time_ns) FROM frames").fetchone()[0]
    if max_recv_ns is None:
        return 0
    return max_recv_ns - int(last_minutes * 60 * 1_000_000_000)


def summarize(db_path, last_minutes=None):
    with sqlite3.connect(db_path) as db:
        if not table_exists(db, "frames") or not table_exists(db, "metrics"):
            raise SystemExit(f"{db_path} does not contain receiver frames/metrics tables")

        frame_cols = column_names(db, "frames")
        metric_cols = column_names(db, "metrics")

        cutoff_ns = cutoff_from_db(db, last_minutes)

        frame_where = "WHERE recv_time_ns >= ?" if cutoff_ns is not None else ""
        metric_where = "WHERE window_end_ns >= ?" if cutoff_ns is not None else ""
        params = (cutoff_ns,) if cutoff_ns is not None else ()

        db_metadata = load_latest_db_metadata(db)

        frame_count, first_recv_ns, last_recv_ns = db.execute(
            f"SELECT COUNT(*), MIN(recv_time_ns), MAX(recv_time_ns) FROM frames {frame_where}",
            params,
        ).fetchone()
        duration_s = (last_recv_ns - first_recv_ns) / 1_000_000_000.0 if frame_count and first_recv_ns else 0.0

        seq_min, seq_max = db.execute(f"SELECT MIN(seq), MAX(seq) FROM frames {frame_where}", params).fetchone()
        expected_frames = (seq_max - seq_min + 1) if seq_min is not None and seq_max is not None else 0
        total_missing_by_seq = max(expected_frames - frame_count, 0)
        ordered_seq = [row[0] for row in db.execute(f"SELECT seq FROM frames {frame_where} ORDER BY seq", params)]
        longest_missing_run = 0
        missing_by_gaps = 0
        previous_seq = None
        for seq in ordered_seq:
            if previous_seq is not None and seq > previous_seq + 1:
                gap = seq - previous_seq - 1
                missing_by_gaps += gap
                longest_missing_run = max(longest_missing_run, gap)
            previous_seq = seq

        metric_rows = db.execute(
            f"""
            SELECT fps, rate_kib_s, missing_frames, loss_rate, crc_errors, old_frames,
                   avg_interval_ms, interval_jitter_ms, bandwidth_jitter_kib_s
            FROM metrics
            {metric_where}
            """,
            params,
        ).fetchall()
        fps = [row[0] for row in metric_rows]
        rates = [row[1] for row in metric_rows]
        missing = [row[2] for row in metric_rows]
        loss_rates = [row[3] for row in metric_rows]
        crc_errors = [row[4] for row in metric_rows]
        old_frames = [row[5] for row in metric_rows]
        interval_jitter = [row[7] for row in metric_rows]
        bandwidth_jitter = [row[8] for row in metric_rows]

        latencies = []
        relative_latencies = []
        if "latency_ms" in frame_cols:
            latency_where = "WHERE latency_ms IS NOT NULL"
            latency_params = ()
            if cutoff_ns is not None:
                latency_where += " AND recv_time_ns >= ?"
                latency_params = (cutoff_ns,)
            latencies = [
                row[0]
                for row in db.execute(f"SELECT latency_ms FROM frames {latency_where}", latency_params)
            ]
        if "relative_latency_ms" in frame_cols:
            relative_latency_where = "WHERE relative_latency_ms IS NOT NULL"
            relative_latency_params = ()
            if cutoff_ns is not None:
                relative_latency_where += " AND recv_time_ns >= ?"
                relative_latency_params = (cutoff_ns,)
            relative_latencies = [
                row[0]
                for row in db.execute(f"SELECT relative_latency_ms FROM frames {relative_latency_where}", relative_latency_params)
            ]
        else:
            relative_rows = db.execute(
                f"""
                SELECT recv_time_ns, send_ts_us
                FROM frames
                {frame_where}
                ORDER BY recv_time_ns
                """,
                params,
            ).fetchall()
            if relative_rows:
                first_recv_ns, first_send_ts_us = relative_rows[0]
                relative_latencies = [
                    (recv_time_ns - first_recv_ns) / 1_000_000.0 - (send_ts_us - first_send_ts_us) / 1_000.0
                    for recv_time_ns, send_ts_us in relative_rows
                ]

        latency_metrics = []
        if "latency_p95_ms" in metric_cols:
            latency_metric_where = "WHERE latency_p95_ms IS NOT NULL"
            latency_metric_params = ()
            if cutoff_ns is not None:
                latency_metric_where += " AND window_end_ns >= ?"
                latency_metric_params = (cutoff_ns,)
            latency_metrics = [
                row[0]
                for row in db.execute(
                    f"SELECT latency_p95_ms FROM metrics {latency_metric_where}",
                    latency_metric_params,
                )
            ]

    return {
        "db_path": str(db_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "capture_start_utc": iso_from_ns(first_recv_ns),
        "capture_end_utc": iso_from_ns(last_recv_ns),
        "time_filter": f"last {last_minutes:g} minutes" if last_minutes is not None else "all data",
        "db_metadata": db_metadata,
        "frame_count": frame_count,
        "duration_s": duration_s,
        "seq_min": seq_min,
        "seq_max": seq_max,
        "expected_frames": expected_frames,
        "total_missing_by_seq": total_missing_by_seq,
        "missing_frames_by_gaps": missing_by_gaps,
        "longest_missing_run": longest_missing_run,
        "missing_frames_window_sum": sum(missing),
        "loss_rate_mean": mean(loss_rates),
        "loss_rate_max": max(loss_rates) if loss_rates else None,
        "crc_errors_total": sum(crc_errors),
        "old_frames_total": sum(old_frames),
        "fps_mean": mean(fps),
        "fps_min": min(fps) if fps else None,
        "fps_max": max(fps) if fps else None,
        "rate_kib_s_mean": mean(rates),
        "rate_kib_s_min": min(rates) if rates else None,
        "rate_kib_s_max": max(rates) if rates else None,
        "interval_jitter_ms_mean": mean(interval_jitter),
        "interval_jitter_ms_max": max(interval_jitter) if interval_jitter else None,
        "bandwidth_jitter_kib_s_mean": mean(bandwidth_jitter),
        "bandwidth_jitter_kib_s_max": max(bandwidth_jitter) if bandwidth_jitter else None,
        "latency_count": len(latencies),
        "latency_avg_ms": mean(latencies),
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
        "latency_p99_ms": percentile(latencies, 99),
        "relative_latency_count": len(relative_latencies),
        "relative_latency_avg_ms": mean(relative_latencies),
        "relative_latency_p50_ms": percentile(relative_latencies, 50),
        "relative_latency_p95_ms": percentile(relative_latencies, 95),
        "relative_latency_p99_ms": percentile(relative_latencies, 99),
        "latency_window_p95_max_ms": max(latency_metrics) if latency_metrics else None,
    }


def load_metric_series(db_path, last_minutes=None):
    with sqlite3.connect(db_path) as db:
        cutoff_ns = cutoff_from_db(db, last_minutes)
        metric_where = "WHERE window_end_ns >= ?" if cutoff_ns is not None else ""
        params = (cutoff_ns,) if cutoff_ns is not None else ()
        metric_cols = column_names(db, "metrics")
        latency_cols = [
            col for col in ("latency_avg_ms", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms")
            if col in metric_cols
        ]
        select_cols = [
            "window_end_ns", "fps", "rate_kib_s", "missing_frames", "loss_rate",
            "crc_errors", "avg_interval_ms", "interval_jitter_ms", "bandwidth_jitter_kib_s",
        ] + latency_cols
        rows = db.execute(
            f"SELECT {', '.join(select_cols)} FROM metrics {metric_where} ORDER BY window_end_ns",
            params,
        ).fetchall()
        if not rows:
            return []
        first_ns = rows[0][0]
        series = []
        for row in rows:
            item = {col: row[idx] for idx, col in enumerate(select_cols)}
            item["t_s"] = (item["window_end_ns"] - first_ns) / 1_000_000_000.0
            series.append(item)
        return series


def load_latency_samples(db_path, last_minutes=None):
    with sqlite3.connect(db_path) as db:
        if "latency_ms" not in column_names(db, "frames"):
            return []
        cutoff_ns = cutoff_from_db(db, last_minutes)
        where = "WHERE latency_ms IS NOT NULL"
        params = []
        if cutoff_ns is not None:
            where += " AND recv_time_ns >= ?"
            params.append(cutoff_ns)
        rows = db.execute(
            f"""
            SELECT latency_ms
            FROM frames
            {where}
            ORDER BY recv_time_ns DESC
            LIMIT ?
            """,
            (*params, MAX_LATENCY_HIST_SAMPLES),
        ).fetchall()
        return [row[0] for row in rows]


def load_relative_latency_samples(db_path, last_minutes=None):
    with sqlite3.connect(db_path) as db:
        if "relative_latency_ms" in column_names(db, "frames"):
            cutoff_ns = cutoff_from_db(db, last_minutes)
            where = "WHERE relative_latency_ms IS NOT NULL"
            params = []
            if cutoff_ns is not None:
                where += " AND recv_time_ns >= ?"
                params.append(cutoff_ns)
            rows = db.execute(
                f"""
                SELECT relative_latency_ms
                FROM frames
                {where}
                ORDER BY recv_time_ns DESC
                LIMIT ?
                """,
                (*params, MAX_LATENCY_HIST_SAMPLES),
            ).fetchall()
            return [row[0] for row in rows]

        rows = db.execute(
            """
            SELECT recv_time_ns, send_ts_us
            FROM frames
            ORDER BY recv_time_ns
            """,
        ).fetchall()
        if not rows:
            return []
        first_recv_ns, first_send_ts_us = rows[0]
        samples = []
        for recv_time_ns, send_ts_us in rows:
            samples.append(
                (recv_time_ns - first_recv_ns) / 1_000_000.0 - (send_ts_us - first_send_ts_us) / 1_000.0
            )
        return samples[-MAX_LATENCY_HIST_SAMPLES:]


def write_plots(summary, db_path, out_dir, stamp, last_minutes=None):
    try:
        import matplotlib
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "matplotlib is required to write PNG report figures. "
            "Install it in this Python environment with: python -m pip install matplotlib "
            "or rerun via tools/run_udp_field_test.py / tools/generate_latest_udp_report.py."
        ) from exc

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = load_metric_series(db_path, last_minutes)
    if not series:
        return []
    target_fps = parse_optional_float(summary.get("target_fps"))
    target_rate_kib_s = parse_optional_float(summary.get("target_rate_kib_s"))

    figure_dir = out_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    t = [row["t_s"] / 60.0 for row in series]

    fig, axes = plt.subplots(2, 2, figsize=(12, 7), constrained_layout=True)
    fig.suptitle("ESP32-S3 Neural Stream Metrics", fontsize=14, fontweight="bold")

    axes[0, 0].plot(t, [row["rate_kib_s"] for row in series], color="#1f77b4", linewidth=1.8, label="observed")
    if target_rate_kib_s is not None:
        axes[0, 0].axhline(target_rate_kib_s, color="#444444", linestyle="--", linewidth=1.0, label="target")
    axes[0, 0].set_title("Throughput")
    axes[0, 0].set_ylabel("KiB/s")
    axes[0, 0].legend(loc="best", fontsize=8)

    axes[0, 1].plot(t, [row["fps"] for row in series], color="#2ca02c", linewidth=1.8)
    if target_fps is not None:
        axes[0, 1].axhline(target_fps, color="#444444", linestyle="--", linewidth=1.0)
    axes[0, 1].set_title("Frame Rate")
    axes[0, 1].set_ylabel("fps")

    axes[1, 0].plot(t, [(row["loss_rate"] or 0.0) * 100.0 for row in series], color="#d62728", linewidth=1.6, label="loss")
    axes[1, 0].bar(t, [row["crc_errors"] or 0 for row in series], width=0.025, alpha=0.25, color="#7f7f7f", label="CRC errors")
    axes[1, 0].set_title("Loss and Parser Integrity")
    axes[1, 0].set_ylabel("loss % / CRC count")
    axes[1, 0].legend(loc="best", fontsize=8)

    axes[1, 1].plot(t, [row["interval_jitter_ms"] for row in series], color="#9467bd", linewidth=1.6, label="arrival jitter")
    if "latency_p95_ms" in series[0]:
        axes[1, 1].plot(t, [row.get("latency_p95_ms") for row in series], color="#ff7f0e", linewidth=1.6, label="latency P95")
    axes[1, 1].set_title("Timing Stability")
    axes[1, 1].set_ylabel("ms")
    axes[1, 1].legend(loc="best", fontsize=8)

    for ax in axes.flat:
        ax.set_xlabel("minutes")
        ax.grid(True, alpha=0.25)

    timeseries_path = figure_dir / f"bandwidth_timeseries_{stamp}.png"
    fig.savefig(timeseries_path, dpi=160)
    plt.close(fig)

    written = [timeseries_path]
    abs_latencies = load_latency_samples(db_path, last_minutes)
    rel_latencies = load_relative_latency_samples(db_path, last_minutes)
    if abs_latencies or rel_latencies:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), constrained_layout=True)
        if abs_latencies:
            axes[0].hist(abs_latencies, bins=60, color="#1f77b4", alpha=0.85)
            if summary.get("latency_p50_ms") is not None:
                axes[0].axvline(summary["latency_p50_ms"], color="#2ca02c", linestyle="--", linewidth=1.5, label="P50")
            if summary.get("latency_p95_ms") is not None:
                axes[0].axvline(summary["latency_p95_ms"], color="#ff7f0e", linestyle="--", linewidth=1.5, label="P95")
            if summary.get("latency_p99_ms") is not None:
                axes[0].axvline(summary["latency_p99_ms"], color="#d62728", linestyle="--", linewidth=1.5, label="P99")
            axes[0].set_title("Absolute latency")
            axes[0].set_xlabel("latency (ms)")
            axes[0].set_ylabel("frames")
            axes[0].legend(loc="best")
        else:
            axes[0].text(0.5, 0.5, "Absolute latency unavailable", ha="center", va="center")
            axes[0].set_axis_off()

        if rel_latencies:
            axes[1].hist(rel_latencies, bins=60, color="#6f42c1", alpha=0.85)
            rel_p50 = summary.get("relative_latency_p50_ms")
            rel_p95 = summary.get("relative_latency_p95_ms")
            rel_p99 = summary.get("relative_latency_p99_ms")
            if rel_p50 is not None:
                axes[1].axvline(rel_p50, color="#2ca02c", linestyle="--", linewidth=1.5, label="P50")
            if rel_p95 is not None:
                axes[1].axvline(rel_p95, color="#ff7f0e", linestyle="--", linewidth=1.5, label="P95")
            if rel_p99 is not None:
                axes[1].axvline(rel_p99, color="#d62728", linestyle="--", linewidth=1.5, label="P99")
            axes[1].set_title("Relative latency from first packet")
            axes[1].set_xlabel("latency (ms)")
            axes[1].set_ylabel("frames")
            axes[1].legend(loc="best")
        else:
            axes[1].text(0.5, 0.5, "Relative latency unavailable", ha="center", va="center")
            axes[1].set_axis_off()

        for ax in axes:
            ax.grid(True, alpha=0.25)
        latency_path = figure_dir / f"latency_histogram_{stamp}.png"
        fig.savefig(latency_path, dpi=160)
        plt.close(fig)
        written.append(latency_path)
    else:
        fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
        ax.text(
            0.5,
            0.56,
            "Latency unavailable",
            ha="center",
            va="center",
            fontsize=18,
            fontweight="bold",
        )
        ax.text(
            0.5,
            0.42,
            "No packet timestamps were captured for this run.",
            ha="center",
            va="center",
            fontsize=11,
        )
        ax.set_axis_off()
        latency_path = figure_dir / f"latency_histogram_{stamp}.png"
        fig.savefig(latency_path, dpi=160)
        plt.close(fig)
        written.append(latency_path)

    return written


def write_summary_csv(summary, path):
    csv_summary = dict(summary)
    csv_summary.pop("db_metadata", None)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_summary.keys()))
        writer.writeheader()
        writer.writerow(csv_summary)


def copy_report_figures_to_capture(db_path, figure_paths):
    capture_dir = Path(db_path).resolve().parent
    if not figure_paths or not capture_dir.exists():
        return []
    capture_figure_dir = capture_dir / "figures"
    capture_figure_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for figure_path in figure_paths:
        figure_path = Path(figure_path)
        destination = capture_figure_dir / figure_path.name
        if figure_path.resolve() != destination.resolve():
            shutil.copy2(figure_path, destination)
        copied.append(destination)
    return copied


def attach_manifest_fields(summary, manifest):
    metadata = {}
    metadata.update(manifest or {})
    metadata.update(summary.get("db_metadata") or {})
    if isinstance(manifest, dict) and isinstance(manifest.get("network"), dict):
        network = dict(metadata.get("network") or {})
        network.update(manifest["network"])
        metadata["network"] = network
    condition = metadata.get("condition") if isinstance(metadata.get("condition"), dict) else {}
    summary["experiment_id"] = metadata.get("experiment_id", "")
    summary["condition_label"] = metadata.get("condition_label", "")
    summary["transport"] = metadata.get("transport", metadata.get("stream", {}).get("transport", ""))
    summary["payload_bytes"] = metadata.get("payload_bytes", metadata.get("stream", {}).get("payload_bytes", ""))
    summary["frame_bytes"] = metadata.get("frame_bytes", metadata.get("stream", {}).get("frame_bytes", ""))
    target_fps = metadata.get("target_fps", metadata.get("stream", {}).get("target_fps", ""))
    if str(target_fps).lower() == "unlimited":
        search_text = " ".join(
            str(metadata.get(key, ""))
            for key in ("condition_label", "operator_notes", "experiment_id")
        )
        match = re.search(r"\b(\d+(?:\.\d+)?)\s*fps\b", search_text, flags=re.IGNORECASE)
        if match:
            target_fps = match.group(1)
    summary["target_fps"] = target_fps
    target_fps = parse_optional_float(summary["target_fps"])
    if summary["frame_bytes"] not in ("", None) and target_fps is not None:
        summary["target_rate_kib_s"] = float(summary["frame_bytes"]) * target_fps / 1024.0
    else:
        summary["target_rate_kib_s"] = ""
    summary["read_limit_kib_s"] = metadata.get("read_limit_kib_s", condition.get("receiver_read_limit_kib_s", ""))
    summary["distance_m"] = condition.get("distance_m", "")
    return summary


def write_markdown(summary, manifest, path, figure_paths=None):
    metadata = {}
    metadata.update(manifest or {})
    metadata.update(summary.get("db_metadata") or {})
    if isinstance(manifest, dict) and isinstance(manifest.get("network"), dict):
        network = dict(metadata.get("network") or {})
        network.update(manifest["network"])
        metadata["network"] = network
    transport_value = str(summary.get("transport") or metadata.get("transport") or "").lower()
    is_udp = "udp" in transport_value
    transport_name = "UDP" if is_udp else "TCP"
    payload_label = f"{summary.get('target_fps') or 'configured'} fps x {summary.get('payload_bytes') or 'configured'} byte"
    if is_udp:
        context_text = (
            "This report summarizes an ESP32-S3 WiFi/UDP stream used as a neural-data surrogate for downstream "
            "spike-sorting and compression experiments. The main engineering question is how much packetized "
            "throughput the wireless link can sustain while keeping sequence-gap loss, CRC errors, jitter, and "
            "end-to-end latency within an acceptable range."
        )
        jitter_note = (
            "Arrival jitter captures UDP datagram cadence variability; sequence gaps represent application-visible "
            "packet loss rather than TCP backpressure."
        )
    else:
        context_text = (
            "This report summarizes an ESP32-S3 WiFi/TCP stream used as a neural-data surrogate for downstream "
            "spike-sorting and compression experiments. The main engineering question is whether the wireless link "
            "can sustain the configured stream rate while keeping application frame loss, parser errors, jitter, "
            "and end-to-end latency within an acceptable range."
        )
        jitter_note = "Arrival jitter captures WiFi/TCP cadence variability even when TCP eventually delivers every byte."
    manifest_text = json.dumps(metadata, indent=2) if metadata else "No manifest or DB run metadata supplied."
    gate_rows = "\n".join(
        f"| {gate['gate']} | {gate['status']} | {gate['value']} | {gate['criterion']} |"
        for gate in quality_gates(summary)
    )
    figures = ""
    if figure_paths:
        figure_lines = ["## Figures", ""]
        for figure_path in figure_paths:
            rel_path = figure_path.relative_to(path.parent).as_posix()
            title = figure_path.stem.replace("_", " ").title()
            figure_lines.append(f"![{title}]({rel_path})")
            figure_lines.append("")
        figures = "\n".join(figure_lines)
    content = f"""# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `{summary['generated_at']}`

## Experiment Context

{context_text}

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | {summary['time_filter']} |
| Capture start UTC | {summary['capture_start_utc'] or 'n/a'} |
| Capture end UTC | {summary['capture_end_utc'] or 'n/a'} |
| Captured frames | {summary['frame_count']} |
| Capture duration | {fmt(summary['duration_s'], 2, ' s')} |
| Transport | {summary.get('transport') or 'n/a'} |
| Payload bytes | {summary.get('payload_bytes') or 'n/a'} |
| Frame bytes | {summary.get('frame_bytes') or 'n/a'} |
| Target FPS | {summary.get('target_fps') or 'n/a'} |
| Target throughput | {fmt(parse_optional_float(summary.get('target_rate_kib_s')), 2, ' KiB/s')} |
| Mean FPS | {fmt(summary['fps_mean'], 2)} |
| FPS range | {fmt(summary['fps_min'], 2)} - {fmt(summary['fps_max'], 2)} |
| Mean throughput | {fmt(summary['rate_kib_s_mean'], 2, ' KiB/s')} |
| Throughput range | {fmt(summary['rate_kib_s_min'], 2)} - {fmt(summary['rate_kib_s_max'], 2)} KiB/s |
| Total missing frames by sequence | {summary['total_missing_by_seq']} |
| Missing frames by in-window gaps | {summary['missing_frames_by_gaps']} |
| Longest consecutive missing run | {summary['longest_missing_run']} |
| Window missing-frame sum | {summary['missing_frames_window_sum']} |
| Mean loss rate | {fmt(summary['loss_rate_mean'] * 100 if summary['loss_rate_mean'] is not None else None, 4, '%')} |
| Max loss rate | {fmt(summary['loss_rate_max'] * 100 if summary['loss_rate_max'] is not None else None, 4, '%')} |
| CRC/resync errors | {summary['crc_errors_total']} |
| Old/duplicate frames | {summary['old_frames_total']} |
| Mean arrival jitter | {fmt(summary['interval_jitter_ms_mean'], 3, ' ms')} |
| Max arrival jitter | {fmt(summary['interval_jitter_ms_max'], 3, ' ms')} |
| Mean bandwidth volatility | {fmt(summary['bandwidth_jitter_kib_s_mean'], 3, ' KiB/s')} |
| Max bandwidth volatility | {fmt(summary['bandwidth_jitter_kib_s_max'], 3, ' KiB/s')} |
| Latency samples | {summary['latency_count']} |
| Mean latency | {fmt(summary['latency_avg_ms'], 3, ' ms')} |
| P50 latency | {fmt(summary['latency_p50_ms'], 3, ' ms')} |
| P95 latency | {fmt(summary['latency_p95_ms'], 3, ' ms')} |
| P99 latency | {fmt(summary['latency_p99_ms'], 3, ' ms')} |
| Relative latency samples | {summary.get('relative_latency_count', 0)} |
| Mean relative latency | {fmt(summary.get('relative_latency_avg_ms'), 3, ' ms')} |
| P50 relative latency | {fmt(summary.get('relative_latency_p50_ms'), 3, ' ms')} |
| P95 relative latency | {fmt(summary.get('relative_latency_p95_ms'), 3, ' ms')} |
| P99 relative latency | {fmt(summary.get('relative_latency_p99_ms'), 3, ' ms')} |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
{gate_rows}

{figures}

## Interpretation Notes

- A healthy {transport_name} run should keep loss rate and CRC/resync errors at zero for the current {payload_label} workload.
- {jitter_note}
- Absolute latency is only trustworthy when both the ESP32-S3 clock and the laptop clock are synchronized.
- Relative latency from the first packet is useful even when the laptop clock is not synchronized, because it removes the fixed clock offset and still shows queue buildup.
- If absolute latency looks suspiciously large, prefer the relative-latency panel and repeat the run with working NTP before drawing one-way latency conclusions.
- Treat the quality gates as screening checks. A WARN does not automatically invalidate the run, but it should be explained in the experiment notes.

## Experiment Manifest

```json
{manifest_text}
```
"""
    path.write_text(content, encoding="utf-8")


def refresh_report_browser(out_dir):
    if Path(out_dir).name != "reports":
        return
    try:
        from build_report_browser import build_index

        index_path = build_index(Path(out_dir))
        print(f"Wrote {index_path}")
    except Exception as exc:
        print(f"Report browser index was not refreshed: {exc}")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate an ESP32-S3 bandwidth experiment report")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Receiver SQLite database path")
    parser.add_argument("--out", default="reports", help="Output directory")
    parser.add_argument("--manifest", help="Optional experiment JSON manifest")
    parser.add_argument(
        "--last-minutes",
        type=float,
        help="Only summarize the most recent N minutes in the SQLite database",
    )
    parser.add_argument("--no-plots", action="store_true", help="Skip matplotlib PNG figures")
    return parser.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db)
    requested_out_dir = Path(args.out)
    out_dir = requested_out_dir / "runs" if requested_out_dir.name == "reports" else requested_out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = summarize(db_path, args.last_minutes)
    manifest = load_manifest(args.manifest)
    summary = attach_manifest_fields(summary, manifest)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"bandwidth_report_{stamp}.md"
    csv_path = out_dir / f"bandwidth_summary_{stamp}.csv"
    figure_paths = [] if args.no_plots else write_plots(summary, db_path, out_dir, stamp, args.last_minutes)
    capture_figure_paths = copy_report_figures_to_capture(db_path, figure_paths)

    write_markdown(summary, manifest, md_path, figure_paths)
    write_summary_csv(summary, csv_path)
    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")
    for figure_path in capture_figure_paths:
        print(f"Wrote {figure_path}")
    refresh_report_browser(requested_out_dir)


if __name__ == "__main__":
    main()
