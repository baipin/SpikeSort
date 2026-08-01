import argparse
import csv
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB = Path("captures") / "bandwidth_capture.sqlite3"


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


def summarize(db_path, last_minutes=None):
    with sqlite3.connect(db_path) as db:
        if not table_exists(db, "frames") or not table_exists(db, "metrics"):
            raise SystemExit(f"{db_path} does not contain receiver frames/metrics tables")

        frame_cols = column_names(db, "frames")
        metric_cols = column_names(db, "metrics")

        max_recv_ns = db.execute("SELECT MAX(recv_time_ns) FROM frames").fetchone()[0]
        cutoff_ns = None
        if last_minutes is not None:
            if max_recv_ns is None:
                cutoff_ns = 0
            else:
                cutoff_ns = max_recv_ns - int(last_minutes * 60 * 1_000_000_000)

        frame_where = "WHERE recv_time_ns >= ?" if cutoff_ns is not None else ""
        metric_where = "WHERE window_end_ns >= ?" if cutoff_ns is not None else ""
        params = (cutoff_ns,) if cutoff_ns is not None else ()

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
        "time_filter": f"last {last_minutes:g} minutes" if last_minutes is not None else "all data",
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
        "latency_window_p95_max_ms": max(latency_metrics) if latency_metrics else None,
    }


def write_summary_csv(summary, path):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)


def write_markdown(summary, manifest, path):
    manifest_text = json.dumps(manifest, indent=2) if manifest else "No manifest supplied."
    content = f"""# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `{summary['generated_at']}`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/TCP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is whether the wireless link can sustain the configured stream rate while keeping application frame loss, parser errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | {summary['time_filter']} |
| Captured frames | {summary['frame_count']} |
| Capture duration | {fmt(summary['duration_s'], 2, ' s')} |
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

## Interpretation Notes

- A healthy run should keep loss rate and CRC/resync errors at zero for the current 20 fps x 4 KiB workload.
- Arrival jitter captures WiFi/TCP cadence variability even when TCP eventually delivers every byte.
- Latency is available only when the ESP32-S3 SNTP clock sync succeeds and the laptop clock is also synchronized.
- If latency is unavailable, use throughput, frame cadence, and jitter for link stability, then repeat the run with working NTP before drawing latency conclusions.

## Experiment Manifest

```json
{manifest_text}
```
"""
    path.write_text(content, encoding="utf-8")


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
    return parser.parse_args()


def main():
    args = parse_args()
    db_path = Path(args.db)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = summarize(db_path, args.last_minutes)
    manifest = load_manifest(args.manifest)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = out_dir / f"bandwidth_report_{stamp}.md"
    csv_path = out_dir / f"bandwidth_summary_{stamp}.csv"

    write_markdown(summary, manifest, md_path)
    write_summary_csv(summary, csv_path)
    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
