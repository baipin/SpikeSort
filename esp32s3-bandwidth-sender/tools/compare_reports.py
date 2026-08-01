import argparse
import csv
from datetime import datetime
from pathlib import Path


def parse_float(value):
    if value in (None, "", "None", "n/a"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def load_summary(path):
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    row["summary_path"] = str(path)
    row["label"] = (
        row.get("condition_label")
        or row.get("experiment_id")
        or Path(path).stem.replace("bandwidth_summary_", "")
    )
    return row


def write_combined_csv(rows, path):
    fieldnames = sorted({key for row in rows for key in row.keys()})
    preferred = [
        "label", "time_filter", "capture_start_utc", "capture_end_utc",
        "experiment_id", "condition_label", "read_limit_kib_s", "distance_m",
        "fps_mean", "rate_kib_s_mean", "loss_rate_max", "crc_errors_total",
        "interval_jitter_ms_mean", "latency_p95_ms", "latency_p99_ms",
        "longest_missing_run", "summary_path",
    ]
    ordered = [field for field in preferred if field in fieldnames]
    ordered += [field for field in fieldnames if field not in ordered]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def write_plots(rows, out_dir, stamp):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    labels = [row["label"] for row in rows]
    x = range(len(rows))

    def values(name, default=0.0):
        return [parse_float(row.get(name)) if parse_float(row.get(name)) is not None else default for row in rows]

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), constrained_layout=True)
    fig.suptitle("ESP32-S3 Bandwidth Experiment Comparison", fontsize=14, fontweight="bold")

    axes[0, 0].bar(x, values("rate_kib_s_mean"), color="#1f77b4")
    axes[0, 0].set_title("Mean Throughput")
    axes[0, 0].set_ylabel("KiB/s")

    axes[0, 1].bar(x, values("fps_mean"), color="#2ca02c")
    axes[0, 1].set_title("Mean Frame Rate")
    axes[0, 1].set_ylabel("fps")

    axes[1, 0].bar(x, [v * 100.0 for v in values("loss_rate_max")], color="#d62728")
    axes[1, 0].set_title("Max Loss Rate")
    axes[1, 0].set_ylabel("%")

    axes[1, 1].bar(x, values("latency_p95_ms"), color="#ff7f0e")
    axes[1, 1].set_title("P95 Latency")
    axes[1, 1].set_ylabel("ms")

    for ax in axes.flat:
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=30, ha="right")
        ax.grid(True, axis="y", alpha=0.25)

    comparison_path = out_dir / f"comparison_summary_{stamp}.png"
    fig.savefig(comparison_path, dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 5.5), constrained_layout=True)
    ax.scatter(values("rate_kib_s_mean"), values("latency_p95_ms"), s=80, color="#9467bd")
    for row in rows:
        rate = parse_float(row.get("rate_kib_s_mean"))
        latency = parse_float(row.get("latency_p95_ms"))
        if rate is not None and latency is not None:
            ax.annotate(row["label"], (rate, latency), textcoords="offset points", xytext=(5, 5), fontsize=8)
    ax.set_title("Throughput vs P95 Latency")
    ax.set_xlabel("mean throughput (KiB/s)")
    ax.set_ylabel("P95 latency (ms)")
    ax.grid(True, alpha=0.25)
    tradeoff_path = out_dir / f"throughput_latency_tradeoff_{stamp}.png"
    fig.savefig(tradeoff_path, dpi=160)
    plt.close(fig)

    return [comparison_path, tradeoff_path]


def write_markdown(rows, csv_path, figure_paths, path):
    table_rows = "\n".join(
        "| {label} | {rate} | {fps} | {loss} | {crc} | {jitter} | {latency} |".format(
            label=row["label"],
            rate=row.get("rate_kib_s_mean", ""),
            fps=row.get("fps_mean", ""),
            loss=row.get("loss_rate_max", ""),
            crc=row.get("crc_errors_total", ""),
            jitter=row.get("interval_jitter_ms_mean", ""),
            latency=row.get("latency_p95_ms", ""),
        )
        for row in rows
    )
    figure_text = "\n".join(f"![{p.stem}]({p.relative_to(path.parent).as_posix()})\n" for p in figure_paths)
    content = f"""# ESP32-S3 Bandwidth Experiment Comparison

Combined CSV: `{csv_path.relative_to(path.parent).as_posix()}`

| Run | Mean throughput KiB/s | Mean FPS | Max loss rate | CRC errors | Mean jitter ms | P95 latency ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{table_rows}

## Figures

{figure_text}
"""
    path.write_text(content, encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Compare ESP32-S3 bandwidth report summary CSV files")
    parser.add_argument("--summaries", nargs="+", required=True, help="One or more bandwidth_summary_*.csv files")
    parser.add_argument("--out", default="reports/comparisons", help="Output directory")
    return parser.parse_args()


def main():
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [load_summary(Path(path)) for path in args.summaries]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = out_dir / f"comparison_summary_{stamp}.csv"
    md_path = out_dir / f"comparison_report_{stamp}.md"
    write_combined_csv(rows, csv_path)
    figure_paths = write_plots(rows, out_dir, stamp)
    write_markdown(rows, csv_path, figure_paths, md_path)
    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")
    for path in figure_paths:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
