import argparse
import csv
from pathlib import Path


FRAME_BYTES = 1038


def parse_float(value):
    if value in (None, "", "None", "n/a"):
        return None
    return float(value)


def load_packet_log(path):
    rows = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                {
                    "seq": int(row["seq"]),
                    "recv_time_ns": int(row["recv_time_ns"]),
                    "recv_epoch_ms": int(row["recv_epoch_ms"]),
                    "latency_ms": parse_float(row.get("latency_ms")),
                }
            )
    if not rows:
        raise SystemExit(f"No packet rows found in {path}")
    return rows


def per_second_bins(rows):
    first_ns = rows[0]["recv_time_ns"]
    bins = {}
    previous_seq = None
    for row in rows:
        second = int((row["recv_time_ns"] - first_ns) / 1_000_000_000)
        item = bins.setdefault(second, {"received": 0, "missing": 0})
        item["received"] += 1
        if previous_seq is not None and row["seq"] > previous_seq + 1:
            item["missing"] += row["seq"] - previous_seq - 1
        previous_seq = row["seq"]
    return bins


def percentile(values, pct):
    values = sorted(value for value in values if value is not None)
    if not values:
        return None
    index = (len(values) - 1) * pct / 100.0
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    if lower == upper:
        return values[lower]
    return values[lower] * (upper - index) + values[upper] * (index - lower)


def write_plots(rows, out_dir, stem):
    try:
        import matplotlib
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "matplotlib is required to write UDP packet-log figures. "
            "Install it in this Python environment with: python -m pip install matplotlib "
            "or rerun via tools/generate_latest_udp_report.py."
        ) from exc

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    first_ns = rows[0]["recv_time_ns"]
    t_s = [(row["recv_time_ns"] - first_ns) / 1_000_000_000.0 for row in rows]
    seq = [row["seq"] for row in rows]
    latencies = [row["latency_ms"] for row in rows if row["latency_ms"] is not None]
    intervals_ms = [
        (rows[i]["recv_time_ns"] - rows[i - 1]["recv_time_ns"]) / 1_000_000.0
        for i in range(1, len(rows))
    ]

    bins = per_second_bins(rows)
    seconds = sorted(bins)
    received = [bins[second]["received"] for second in seconds]
    missing = [bins[second]["missing"] for second in seconds]
    throughput_kib_s = [value * FRAME_BYTES / 1024.0 for value in received]
    loss_pct = [
        (miss / (miss + recv) * 100.0) if (miss + recv) else 0.0
        for miss, recv in zip(missing, received)
    ]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9), constrained_layout=True)
    fig.suptitle("UDP max-throughput packet-log overview", fontsize=15, fontweight="bold")

    axes[0, 0].plot(seconds, received, color="#1f77b4", linewidth=1.6, label="received packets/s")
    axes[0, 0].set_title("Receiver packet rate")
    axes[0, 0].set_xlabel("time since first packet (s)")
    axes[0, 0].set_ylabel("packets/s")
    axes[0, 0].grid(True, alpha=0.25)

    axes[0, 1].plot(seconds, throughput_kib_s, color="#2ca02c", linewidth=1.6)
    axes[0, 1].set_title("Received throughput")
    axes[0, 1].set_xlabel("time since first packet (s)")
    axes[0, 1].set_ylabel("KiB/s")
    axes[0, 1].grid(True, alpha=0.25)

    axes[1, 0].bar(seconds, missing, color="#d62728", width=0.9)
    axes[1, 0].set_title("Sequence gaps by second")
    axes[1, 0].set_xlabel("time since first packet (s)")
    axes[1, 0].set_ylabel("missing sequence numbers")
    axes[1, 0].grid(True, axis="y", alpha=0.25)

    axes[1, 1].plot(seconds, loss_pct, color="#9467bd", linewidth=1.6)
    axes[1, 1].set_title("Window loss rate")
    axes[1, 1].set_xlabel("time since first packet (s)")
    axes[1, 1].set_ylabel("loss (%)")
    axes[1, 1].grid(True, alpha=0.25)

    overview_path = out_dir / f"{stem}_overview.png"
    fig.savefig(overview_path, dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)
    axes[0].scatter(t_s, seq, s=2, alpha=0.35, color="#1f77b4")
    axes[0].set_title("Received sequence numbers over time")
    axes[0].set_xlabel("time since first packet (s)")
    axes[0].set_ylabel("sequence number")
    axes[0].grid(True, alpha=0.2)

    axes[1].hist(intervals_ms, bins=120, color="#ff7f0e", alpha=0.85)
    axes[1].axvline(percentile(intervals_ms, 50), color="#2ca02c", linestyle="--", label="P50")
    axes[1].axvline(percentile(intervals_ms, 95), color="#d62728", linestyle="--", label="P95")
    axes[1].set_title("Packet inter-arrival interval")
    axes[1].set_xlabel("interval (ms)")
    axes[1].set_ylabel("count")
    axes[1].legend()
    axes[1].grid(True, alpha=0.2)

    timing_path = out_dir / f"{stem}_timing.png"
    fig.savefig(timing_path, dpi=170)
    plt.close(fig)

    if latencies:
        fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
        ax.hist(latencies, bins=120, color="#17becf", alpha=0.85)
        ax.axvline(percentile(latencies, 50), color="#2ca02c", linestyle="--", label="P50")
        ax.axvline(percentile(latencies, 95), color="#ff7f0e", linestyle="--", label="P95")
        ax.axvline(percentile(latencies, 99), color="#d62728", linestyle="--", label="P99")
        ax.set_title("End-to-end latency distribution")
        ax.set_xlabel("latency (ms)")
        ax.set_ylabel("count")
        ax.legend()
        ax.grid(True, alpha=0.2)
        latency_path = out_dir / f"{stem}_latency.png"
        fig.savefig(latency_path, dpi=170)
        plt.close(fig)
        return [overview_path, timing_path, latency_path]

    return [overview_path, timing_path]


def main():
    parser = argparse.ArgumentParser(description="Visualize ESP32-S3 UDP packet log CSV files.")
    parser.add_argument("packet_log", help="packet_log_*.csv path")
    parser.add_argument("--out-dir", help="Output directory for PNG figures")
    args = parser.parse_args()

    packet_log = Path(args.packet_log)
    out_dir = Path(args.out_dir) if args.out_dir else packet_log.parent / "figures"
    rows = load_packet_log(packet_log)
    written = write_plots(rows, out_dir, packet_log.stem)
    for path in written:
        print(path)


if __name__ == "__main__":
    main()
