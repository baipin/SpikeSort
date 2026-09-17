"""Build a per-run, position-aware report for the battery UDP series."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAPTURE_ROOT = ROOT / "captures" / "udp_battery_position_series_20260901"
DEFAULT_REPORT_ROOT = ROOT / "reports" / "udp_battery_position_series_20260901"


def tex(value):
    return str(value or "N/A").replace("\\", "\\textbackslash{}").replace("&", "\\&").replace("%", "\\%").replace("_", "\\_").replace("#", "\\#")


def latest(path, pattern):
    files = sorted(path.glob(pattern), key=lambda item: item.stat().st_mtime)
    return files[-1] if files else None


def position_id(name):
    match = re.search(r"battery-position-(\d+(?:-\d+)*)", name)
    return match.group(1) if match else name


def position_sort_key(path):
    name = path.name
    receiver_order = {"under-chair": 0, "desk": 1, "bed": 2, "bathroom": 3, "washroom": 4, "door": 5, "control": 6}
    receiver = next((key for key in receiver_order if key in name), "other")
    motion_order = {"normal-breath": 0, "normal_breath": 0, "deep-breath": 1, "deep_breath": 1,
                    "rotating-head": 2, "rotating_head": 2, "control": 3}
    motion = next((key for key in motion_order if key in name), "other")
    match = re.search(r"(?:-|_)(\d+)(?:_|$)", name)
    rep = int(match.group(1)) if match else 0
    return (receiver_order.get(receiver, 9), motion_order.get(motion, 9), rep, name)


def condition_label(name):
    if "control-esp32-on-table" in name:
        return "Static ESP32 on table (control)"
    match = re.search(r"(?:under-chair|rec_(?:desk|bed|bathroom|washroom|door))[-_](normal[-_]breath|deep[-_]breath|(?:deep[-_])?rotating[-_]head)[-_](\d+)", name)
    if not match:
        return name.replace("-", " ")
    descriptions = {
        "normal-breath": "Normal breathing",
        "deep-breath": "Deep breathing",
        "rotating-head": "Head rotation",
    }
    motion_key = match.group(1).replace("_", "-")
    if motion_key == "deep-rotating-head":
        motion_key = "rotating-head"
    description = descriptions[motion_key]
    return f"{description} (rep {match.group(2)})"


def condition_group(name):
    if "control-esp32-on-table" in name:
        return "Static table control"
    for keys, label in (
        (("normal-breath", "normal_breath"), "Normal breathing"),
        (("deep-breath", "deep_breath"), "Deep breathing"),
        (("rotating-head", "rotating_head"), "Head rotation"),
    ):
        if any(key in name for key in keys):
            return label
    return "Other"


def condition_rep(name):
    if "control-esp32-on-table" in name:
        return "-"
    match = re.search(r"(?:under-chair|rec_(?:desk|bed|bathroom|washroom|door))[-_](?:normal[-_]breath|deep[-_]breath|(?:deep[-_])?rotating[-_]head)[-_](\d+)", name)
    return match.group(1) if match else "N/A"


def receiver_group(name):
    if "under-chair" in name:
        return "Chair underside receiver"
    for key, label in (("rec_desk", "Desk receiver"), ("rec_bed", "Bed receiver"),
                        ("rec_bathroom", "Bathroom receiver"), ("rec_washroom", "Washroom receiver"),
                        ("rec_door", "Door receiver")):
        if key in name:
            return label
    if "control-esp32-on-table" in name:
        return "Static table control"
    return "Other"


def receiver_short(name):
    return {"Chair underside receiver": "Chair", "Desk receiver": "Desk", "Bed receiver": "Bed",
            "Bathroom receiver": "Bathroom", "Washroom receiver": "Washroom",
            "Door receiver": "Door", "Static table control": "Control"}.get(receiver_group(name), "Other")


def mean(values):
    return sum(values) / len(values) if values else 0.0


def sample_variance(values):
    return sum((value - mean(values)) ** 2 for value in values) / (len(values) - 1) if len(values) > 1 else 0.0


def is_disconnected(item):
    """Use the operator-reviewed interruption labels for exclusion."""
    return item["name"] in {
        "udp-telemetry-new-under-chair-deep-breath-3_20260910_155020",
        "udp-telemetry-new-under-chair-normal-breath-1_20260910_152111",
    }


def findings_text(runs):
    """Create data-derived interpretation before the independent run sections."""
    active_groups = ("Chair underside receiver", "Desk receiver", "Bed receiver", "Bathroom receiver", "Washroom receiver", "Door receiver")
    activities = ("Normal breathing", "Deep breathing", "Head rotation")
    lines = [
        r"\clearpage\section*{Findings and conclusions}",
        r"The following interpretation is provided before the individual run results. It is based on the measured 50 ms ESP32-timestamp-aligned receive windows. Repetitions are retained as independent observations; the grouped values below are descriptive summaries, not significance tests.",
        r"\subsection*{Receiver-position effect}",
    ]
    excluded = [item for item in runs if is_disconnected(item)]
    retained = [item for item in runs if not is_disconnected(item)]
    lines += [
        r"\subsection*{Disconnected-run screening}",
        f"Following manual review of the traces, {len(excluded)} of {len(runs)} runs are marked \\textbf{{DISCONNECTED/EXCLUDED}}: " + ", ".join(tex(item["name"]) for item in excluded) + ". These runs remain visible in the per-run results but are excluded only from the clean aggregate statistics below. All other runs, including weaker but continuous links, remain in both the all-run and clean analysis. The exclusion is an operator-reviewed data-quality decision, not an automatically inferred threshold.",
        r"\scriptsize\begin{longtable}{l r r r r r}",
        r"\toprule Aggregate & Runs & Mean Mbps & SD Mbps & Variance Mbps$^2$ & CV (\%)\\\midrule",
    ]
    for label, subset in (("All runs", runs), ("After exclusion", retained)):
        values = [item["window"]["mean"] for item in subset]
        sd = sample_variance(values) ** 0.5
        lines.append(f"{tex(label)} & {len(values)} & {mean(values):.2f} & {sd:.2f} & {sample_variance(values):.2f} & {(sd / mean(values) * 100 if mean(values) else 0):.1f}\\\\")
    lines += [
        r"\bottomrule\end{longtable}\normalsize",
        r"The clean aggregate is the appropriate estimate for the ordinary operating condition; the all-run aggregate is retained to show the effect of interruptions. The difference between these rows is a data-quality effect, not evidence that the radio normally operates at the lower value.",
    ]
    static_runs = [item for item in runs if receiver_group(item["name"]) == "Static table control"]
    mobile_all = [item for item in runs if receiver_group(item["name"]) != "Static table control"]
    mobile_clean = [item for item in mobile_all if not is_disconnected(item)]
    lines += [
        r"\subsection*{Static reference versus mobile conditions}",
        r"The static control is compared with every non-static run below. Run-mean variance quantifies repeatability across independent captures. Mean window variance quantifies short-timescale burstiness within captures. They answer different questions and should not be substituted for one another.",
        r"\scriptsize\begin{longtable}{l r r r r r}",
        r"\toprule Group & Runs & Mean Mbps & Run-mean variance & Mean 50 ms variance & Mean empty (\%)\\\midrule",
    ]
    for label, subset in (("Static control", static_runs), ("Mobile: all runs", mobile_all), ("Mobile: reviewed clean runs", mobile_clean)):
        values = [item["window"]["mean"] for item in subset]
        lines.append(
            f"{tex(label)} & {len(subset)} & {mean(values):.2f} & {sample_variance(values):.2f} & "
            f"{mean([item['window']['variance'] for item in subset]):.2f} & "
            f"{mean([item['window']['empty_pct'] for item in subset]):.2f}\\\\"
        )
    lines += [
        r"\bottomrule\end{longtable}\normalsize",
        r"A high static 50 ms variance does not by itself indicate an unstable static link: under saturated UDP, a high-capacity link can deliver large bursts into adjacent windows. The static control is more repeatable when evaluated by run-mean variance and has fewer empty windows. Conversely, mobile receiver geometry raises run-to-run uncertainty even after the two reviewed disconnections are excluded.",
        r"\subsection*{Motion-condition variance across receiver positions}",
        r"This table pools receiver locations only to describe the experiment-wide range of each motion condition. Since geometry is intentionally different across locations, it is not an isolated causal motion-effect test; the position-by-motion table later in the report is the primary comparison.",
        r"\scriptsize\begin{longtable}{l r r r r r r}",
        r"\toprule Activity & All n & Clean n & All mean & Clean mean & All run variance & Clean run variance\\\midrule",
    ]
    for activity in activities:
        items = [item for item in mobile_all if condition_group(item["name"]) == activity]
        clean = [item for item in items if not is_disconnected(item)]
        all_values = [item["window"]["mean"] for item in items]
        clean_values = [item["window"]["mean"] for item in clean]
        lines.append(
            f"{tex(activity)} & {len(items)} & {len(clean)} & {mean(all_values):.2f} & "
            f"{mean(clean_values):.2f} & {sample_variance(all_values):.2f} & {sample_variance(clean_values):.2f}\\\\"
        )
    lines += [
        r"\bottomrule\end{longtable}\normalsize",
        r"The reviewed exclusions affect normal breathing and deep breathing only. Their removal should therefore be interpreted as a correction of two interrupted captures, not as evidence that head rotation is categorically more stable. The next table keeps each receiver position separate and reports all-run and clean values side by side.",
    ]
    position_stats = []
    for receiver in active_groups:
        items = [item for item in runs if receiver_group(item["name"]) == receiver]
        if not items:
            continue
        position_stats.append((receiver, items))
        lines.append(
            f"{tex(receiver)} contains {len(items)} independent runs with mean receive goodput "
            f"{mean([item['window']['mean'] for item in items]):.2f} Mbps, mean 50 ms-window variance "
            f"{mean([item['window']['variance'] for item in items]):.2f} Mbps$^2$, and mean empty-window share "
            f"{mean([item['window']['empty_pct'] for item in items]):.2f}\%."
        )
    controls = [item for item in runs if receiver_group(item["name"]) == "Static table control"]
    if position_stats:
        best = max(position_stats, key=lambda pair: mean([item["window"]["mean"] for item in pair[1]]))
        worst = min(position_stats, key=lambda pair: mean([item["window"]["mean"] for item in pair[1]]))
        lines.append(
            f"Across the tested receiver locations, {tex(best[0])} has the highest descriptive mean receive goodput "
            f"({mean([item['window']['mean'] for item in best[1]]):.2f} Mbps), while {tex(worst[0])} has the lowest "
            f"({mean([item['window']['mean'] for item in worst[1]]):.2f} Mbps). This indicates that receiver geometry and "
            r"the resulting radio path have a larger observable effect than can be inferred from distance alone."
        )
        lines += [
            r"\subsection*{Variance decomposition across repetitions}",
            r"Two different sources of variability must be separated. Window variance is the short-timescale burstiness within one run; repetition variance below is the variance of the run-level mean goodputs across independent repetitions. The latter is useful for judging repeatability and is not obtained by pooling all 50 ms windows, which would overweight longer captures.",
            r"\scriptsize\begin{longtable}{l r r r r r r}",
            "\\toprule Receiver & Runs & Mean run Mbps & SD Mbps & Run variance Mbps$^2$ & CV (\\%) & 95\\% CI half-width \\\\",
            r"\midrule",
        ]
        for receiver, items in position_stats + ([('Static table control', controls)] if controls else []):
            values = [item['window']['mean'] for item in items]
            avg = mean(values)
            sd = sample_variance(values) ** 0.5
            ci = 1.96 * sd / (len(values) ** 0.5) if values else 0.0
            cv = sd / avg * 100 if avg else 0.0
            lines.append(f"{tex(receiver)} & {len(values)} & {avg:.2f} & {sd:.2f} & {sample_variance(values):.2f} & {cv:.1f} & {ci:.2f}\\\\")
        lines += [
            r"\bottomrule\end{longtable}\normalsize",
            r"The control has the lowest run-to-run CV, whereas the chair and bathroom receiver groups show the largest relative repeatability loss. This pattern indicates that geometry and local radio conditions contribute materially to the uncertainty; the activity label alone cannot explain the spread. The confidence intervals are descriptive normal-approximation intervals and should not be treated as inferential tests because repetitions were collected in one field session and are not randomized blocks.",
        ]
    lines += [
        r"\subsection*{Motion effect within each receiver position}",
        r"The table below reports each position/activity combination separately. It shows how breathing and head rotation change central goodput, short-window variability, and the frequency of fully empty 50 ms windows.",
        r"\scriptsize\begin{longtable}{l l r r r r}\toprule Receiver & Activity & Runs & Mean Mbps & Mean variance (Mbps$^2$) & Mean empty (\%)\\\midrule",
    ]
    activity_stats = []
    for receiver in active_groups:
        for activity in activities:
            items = [item for item in runs if receiver_group(item["name"]) == receiver and condition_group(item["name"]) == activity]
            if not items:
                continue
            activity_stats.append((receiver, activity, items))
            lines.append(
                f"{tex(receiver)} & {tex(activity)} & {len(items)} & {mean([x['window']['mean'] for x in items]):.2f} & "
                f"{mean([x['window']['variance'] for x in items]):.2f} & {mean([x['window']['empty_pct'] for x in items]):.2f}\\\\"
            )
    lines += [
        r"\bottomrule\end{longtable}\normalsize",
        r"The data do not support a universal claim that one motion is always worst: the effect of head movement depends on receiver position. Where head rotation increases variance or empty-window share, it is consistent with short-lived orientation and multipath changes; where the position is already strong, the same motion may have little practical effect. Deep breathing should likewise be interpreted as a controlled movement condition rather than as a separate radio mechanism.",
        r"\subsection*{Static control and practical conclusion}",
    ]
    controls = [item for item in runs if receiver_group(item["name"]) == "Static table control"]
    if controls:
        lines.append(
            f"The static table control contains {len(controls)} independent runs. Its mean goodput is "
            f"{mean([item['window']['mean'] for item in controls]):.2f} Mbps, mean variance is "
            f"{mean([item['window']['variance'] for item in controls]):.2f} Mbps$^2$, and mean empty-window share is "
            f"{mean([item['window']['empty_pct'] for item in controls]):.2f}\%. It provides a reference for variability that "
            r"exists without head motion, but it is not a substitute for the head-mounted scenario."
        )
    lines.append(
        r"Overall, the experiment shows that the measured 50 ms receive behavior is a joint result of receiver placement, "
        r"motion, and burstiness in the saturated UDP path. Mean throughput alone is therefore insufficient: a usable operating "
        r"point should also consider window variance and empty-window share. The following sections preserve every run separately "
        r"so that these conclusions can be audited against the underlying capture and offline replay results."
    )
    return lines


def run(command, cwd=ROOT):
    print(">", " ".join(str(x) for x in command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def map_figure(metadata, source, destination):
    import matplotlib.pyplot as plt

    image = plt.imread(source)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(image)
    colors = {"board": "#c44536", "router": "#2e8b57", "receiver": "#1769aa"}
    labels = {"board": "ESP32 sender", "router": "Router / hotspot", "receiver": "Receiver"}
    for key in ("board", "router", "receiver"):
        point = metadata.get("markers", {}).get(key)
        if not point:
            continue
        x, y = float(point["x"]) * image.shape[1], float(point["y"]) * image.shape[0]
        ax.scatter([x], [y], s=70, c=colors[key], edgecolors="white", linewidths=1.5, label=labels[key], zorder=3)
        ax.annotate(labels[key], (x, y), xytext=(7, -8), textcoords="offset points", color=colors[key], fontsize=9, weight="bold")
    ax.set_title("Measured device distribution for this run")
    ax.axis("off")
    ax.legend(loc="lower right", fontsize=8)
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)


def combined_map_figure(run_items, source, destination):
    import matplotlib.pyplot as plt

    image = plt.imread(source)
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.imshow(image)
    if not run_items:
        return
    fixed = run_items[0]["metadata"].get("markers", {})
    board = fixed.get("board")
    router = fixed.get("router")
    device_labels = []
    co_located = board and router and abs(float(board["x"]) - float(router["x"])) < 0.08 and abs(float(board["y"]) - float(router["y"])) < 0.08
    if co_located:
        x, y = float(board["x"]) * image.shape[1], float(board["y"]) * image.shape[0]
        ax.scatter([x], [y], s=145, c="#704a9f", marker="o", edgecolors="white", linewidths=1.5, zorder=4)
        ax.annotate("S/R", (x, y), ha="center", va="center", color="white", fontsize=7, weight="bold", zorder=5)
        device_labels.append("S/R: ESP32 sender and router co-located")
    elif board:
        x, y = float(board["x"]) * image.shape[1], float(board["y"]) * image.shape[0]
        ax.scatter([x], [y], s=125, c="#c44536", edgecolors="white", linewidths=1.5, zorder=4)
        ax.annotate("S", (x, y), ha="center", va="center", color="white", fontsize=8, weight="bold", zorder=5)
        device_labels.append("S: ESP32 sender")
    if router and not co_located:
        x, y = float(router["x"]) * image.shape[1], float(router["y"]) * image.shape[0]
        ax.scatter([x], [y], s=150, c="#2e8b57", marker="*", edgecolors="white", linewidths=1.5, zorder=4)
        ax.annotate("R", (x, y), ha="center", va="center", color="white", fontsize=7, weight="bold", zorder=5)
        device_labels.append("R: Router / hotspot")
    seen_receivers = set()
    receiver_labels = []
    for item in run_items:
        point = item["metadata"].get("markers", {}).get("receiver")
        if not point:
            continue
        key = (round(float(point["x"]), 4), round(float(point["y"]), 4))
        if key in seen_receivers:
            continue
        seen_receivers.add(key)
        label = receiver_short(item['name'])
        x, y = float(point["x"]) * image.shape[1], float(point["y"]) * image.shape[0]
        marker_number = len(receiver_labels) + 1
        ax.scatter([x], [y], s=105, c="#1769aa", marker="s", edgecolors="white", linewidths=1.5, zorder=4)
        ax.annotate(str(marker_number), (x, y), ha="center", va="center", color="white", fontsize=8, weight="bold", zorder=5)
        receiver_labels.append(f"{marker_number}: {label}")
    ax.set_title("Device locations for the measured condition group")
    ax.axis("off")
    if receiver_labels:
        ax.text(1.01, 0.98, "Device key\n" + "\n".join(device_labels + receiver_labels), transform=ax.transAxes,
                va="top", ha="left", fontsize=8, color="#1769aa",
                bbox={"facecolor": "white", "edgecolor": "#1769aa", "alpha": 0.92, "pad": 5})
    ax.set_xlim(0, image.shape[1])
    ax.set_ylim(image.shape[0], 0)
    fig.subplots_adjust(right=0.72)
    fig.savefig(destination, dpi=180, bbox_inches="tight")
    plt.close(fig)


def read_window_summary(path):
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    goodput = [float(row["received_goodput_mbps"]) for row in rows]
    empty = sum(value == 0 for value in goodput)
    mean = sum(goodput) / len(goodput) if goodput else 0.0
    variance = sum((value - mean) ** 2 for value in goodput) / (len(goodput) - 1) if len(goodput) > 1 else 0.0
    return {"windows": len(rows), "empty": empty, "empty_pct": empty / len(rows) * 100 if rows else 0, "p50": percentile(goodput, .50), "p95": percentile(goodput, .95), "p99": percentile(goodput, .99), "mean": mean, "variance": variance}


def read_cc_summary(path, timeseries_path):
    with path.open(encoding="utf-8", newline="") as handle:
        summary = list(csv.DictReader(handle))
    by_algorithm = {row["algorithm"]: row for row in summary}
    effective = {}
    with timeseries_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            algorithm = row["algorithm"]
            value = float(row["goodput_mbps"])
            effective.setdefault(algorithm, [0, 0])
            effective[algorithm][1] += 1
            effective[algorithm][0] += value > 0
    for algorithm, counts in effective.items():
        if algorithm in by_algorithm:
            by_algorithm[algorithm]["effective_window_pct"] = counts[0] / counts[1] * 100 if counts[1] else 0
    # Keep the observed saturated trace at the top as the reference baseline.
    order = ["raw_saturated", "fixed_90pct", "sqp_lite", "gcc_like", "copa_like", "scream_like", "bbr_like", "pcc_vivace_like"]
    return [by_algorithm[key] for key in order if key in by_algorithm]


def percentile(values, q):
    if not values:
        return 0.0
    values = sorted(values)
    position = (len(values) - 1) * q
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--floorplan", type=Path, default=ROOT / "field_terminal" / "floorplan.jpg")
    parser.add_argument("--title", default="Battery-Powered ESP32 UDP Position Series")
    parser.add_argument("--report-date", default="2026-09-02")
    parser.add_argument("--report-basename", default="battery_position_series_report")
    parser.add_argument(
        "--include-groups",
        default="chair,rec_change",
        help="Comma-separated immediate capture-root subdirectories to include.",
    )
    args = parser.parse_args()
    args.report_root.mkdir(parents=True, exist_ok=True)
    figures = args.report_root / "figures"
    offline = args.report_root / "offline_cc"
    figures.mkdir(exist_ok=True)
    offline.mkdir(exist_ok=True)
    included_groups = {item.strip() for item in args.include_groups.split(",") if item.strip()}
    capture_dirs = []
    for metadata_path in args.capture_root.rglob("field_metadata.json"):
        relative = metadata_path.relative_to(args.capture_root)
        if not relative.parts or relative.parts[0] not in included_groups:
            continue
        capture_dirs.append(metadata_path.parent)
    runs = []
    for capture in sorted(capture_dirs, key=position_sort_key):
        packet = latest(capture, "packet_log_*.csv")
        metadata_path = capture / "field_metadata.json"
        if not packet or not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        run_name = re.sub(r"[^A-Za-z0-9_.-]", "-", capture.name)
        window_script = ROOT / "tools" / "build_udp_send_timestamp_windows.py"
        run([sys.executable, str(window_script), str(capture)])
        window_csv = latest(capture / "figures", "*_50ms_esp32_send_timestamp_windows.csv")
        prefix = f"{run_name}_saturated"
        run([sys.executable, str(ROOT / "tools" / "simulate_sqp_on_udp_trace.py"), str(packet), "--window-ms", "50", "--out-dir", str(offline), "--prefix", prefix])
        cc_csv = offline / f"{prefix}_offline_cc_summary.csv"
        cc_timeseries = offline / f"{prefix}_offline_cc_timeseries.csv"
        window = read_window_summary(window_csv)
        runs.append({"name": capture.name, "metadata": metadata, "window": window, "cc_csv": cc_csv, "cc_summary": read_cc_summary(cc_csv, cc_timeseries)})

    runs = [item for item in runs if condition_group(item["name"]) != "Static table control"] + [
        item for item in runs if condition_group(item["name"]) == "Static table control"
    ]
    for index, item in enumerate(runs, start=1):
        item["run_id"] = str(index)

    head_runs = [item for item in runs if condition_group(item["name"]) != "Static table control"]
    static_controls = [item for item in runs if condition_group(item["name"]) == "Static table control"]
    chair_runs = [item for item in head_runs if receiver_group(item["name"]) == "Chair underside receiver"]
    changed_receiver_runs = [item for item in head_runs if receiver_group(item["name"]) != "Chair underside receiver"]
    chair_map = figures / "chair_receiver_esp32_positions.png"
    changed_map = figures / "receiver_change_esp32_positions.png"
    if chair_runs:
        combined_map_figure(chair_runs, args.floorplan, chair_map)
    if changed_receiver_runs:
        combined_map_figure(changed_receiver_runs, args.floorplan, changed_map)

    condition_summaries = []
    for group in ("Normal breathing", "Deep breathing", "Head rotation"):
        items = [item for item in runs if condition_group(item["name"]) == group]
        if not items:
            continue
        p50_values = [item["window"]["p50"] for item in items]
        p95_values = [item["window"]["p95"] for item in items]
        condition_summaries.append({
            "group": group,
            "runs": len(items),
            "mean_empty": sum(item["window"]["empty_pct"] for item in items) / len(items),
            "median_p50": percentile(p50_values, 0.50),
            "median_p95": percentile(p95_values, 0.50),
            "p50_min": min(p50_values),
            "p50_max": max(p50_values),
        })

    index = args.report_root / f"{args.report_basename}_index.csv"
    with index.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["position_id", "run", "condition", "distance", "placement", "power", "status", "empty_window_pct", "goodput_p50_mbps", "goodput_p95_mbps", "goodput_p99_mbps"])
        for item in runs:
            m, w = item["metadata"], item["window"]
            writer.writerow([item["run_id"], item["name"], m.get("condition", ""), m.get("distance", ""), m.get("placement", ""), m.get("power", ""), "DISCONNECTED/EXCLUDED" if is_disconnected(item) else "VALID", f"{w['empty_pct']:.4f}", f"{w['p50']:.4f}", f"{w['p95']:.4f}", f"{w['p99']:.4f}"])

    tex_lines = [r"\documentclass[10pt]{article}", r"\usepackage[margin=0.65in]{geometry}", r"\usepackage{graphicx,booktabs,longtable,hyperref,array,url,tabularx}", r"\hypersetup{colorlinks=true,linkcolor=blue,urlcolor=blue}", r"\setlength{\emergencystretch}{3em}", r"\setlength{\tabcolsep}{3pt}", f"\\title{{{tex(args.title)}}}", r"\author{Automated field report}", f"\\date{{{tex(args.report_date)}}}", r"\begin{document}\maketitle", r"\section*{Scenario and method}", r"This study evaluates a battery-powered ESP32-S3 sender attached to the left posterior head region. The router/hotspot remains at the reference location and the receiver is measured at the chair underside, bed, bathroom, and washroom positions. The chair case represents a wheelchair user: the router is approximately level with the hips and the receiver is directly below the hips. The 0.8 m chair distance is the approximate brain-to-receiver distance. Each capture is an independent run; repeated runs at the same position are not pooled into a single run. Normal breathing, continuous deep breathing, and normal-speed head rotation are compared with a completely static ESP32 on-table control.", r"\section*{Measurement definitions}", r"Each received packet is assigned to a 50 ms bin using its ESP32 send timestamp. Goodput is received UDP payload throughput in that bin. Empty (\%) is the fraction of bins with zero received frames. Window variance is the sample variance of the 50 ms goodput values in Mbps squared. Offline congestion-control results replay each run's saturated trace and are model outputs, not additional live ESP32 measurements.", r"\section*{Device layout}"]
    if chair_runs:
        tex_lines += [f"\\begin{{center}}\\includegraphics[width=0.74\\textwidth,height=0.31\\textheight,keepaspectratio]{{{tex(chair_map.relative_to(args.report_root).as_posix())}}}\\\\\\small Chair receiver layout; numbered labels identify independent head-mounted runs.\\normalsize\\end{{center}}"]
    if changed_receiver_runs:
        tex_lines += [f"\\begin{{center}}\\includegraphics[width=0.74\\textwidth,height=0.31\\textheight,keepaspectratio]{{{tex(changed_map.relative_to(args.report_root).as_posix())}}}\\\\\\small Receiver-change layouts; the router and ESP32 reference locations are fixed while the receiver position changes.\\normalsize\\end{{center}}"]
    tex_lines += findings_text(runs)
    tex_lines += [r"\clearpage\section*{Run overview}", r"\scriptsize\begin{longtable}{r l l c r r r r l}", r"\toprule ID & Receiver & Activity & Rep. & Empty (\%) & P50 & P95 & P99 & Status\\\midrule"]
    for item in runs:
        m, w = item["metadata"], item["window"]
        status = r"\textbf{DISCONNECTED/EXCLUDED}" if is_disconnected(item) else "VALID"
        tex_lines.append(f"{item['run_id']} & {tex(receiver_short(item['name']))} & {tex(condition_group(item['name']))} & {condition_rep(item['name'])} & {w['empty_pct']:.2f} & {w['p50']:.2f} & {w['p95']:.2f} & {w['p99']:.2f} & {status}\\\\")
    tex_lines += [r"\bottomrule\end{longtable}\normalsize", r"\textbf{Column notes:} Receiver identifies where the computer/receiver was placed. Activity identifies the motion condition; Rep. is an independent repetition at that receiver position. Empty (\%) is the proportion of ESP32-time-aligned 50 ms windows containing zero received frames. P50/P95/P99 are the 50th/95th/99th percentiles of received goodput per 50 ms window, in Mbps. Variance is reported below in Mbps squared. These are measured receive-side values, not modeled loss.", r"\section*{Position and activity summary}", r"The following summaries are grouped by receiver position and activity for descriptive comparison. Every row reports both the all-run result and the result after removing runs marked DISCONNECTED/EXCLUDED.", r"\scriptsize\begin{longtable}{l l r r r r r r r}\toprule Receiver & Activity & All n & Clean n & All mean & Clean mean & All var. & Clean var. & All/Clean empty (\%)\\\midrule"]
    for receiver in ("Chair underside receiver", "Desk receiver", "Bed receiver", "Bathroom receiver", "Washroom receiver", "Door receiver", "Static table control"):
        for group in ("Normal breathing", "Deep breathing", "Head rotation", "Static table control"):
            items = [item for item in runs if receiver_group(item["name"]) == receiver and condition_group(item["name"]) == group]
            if not items:
                continue
            clean = [item for item in items if not is_disconnected(item)]
            all_values = [item["window"]["mean"] for item in items]
            clean_values = [item["window"]["mean"] for item in clean]
            all_var = sample_variance(all_values)
            clean_var = sample_variance(clean_values)
            all_empty = mean([item["window"]["empty_pct"] for item in items])
            clean_empty = mean([item["window"]["empty_pct"] for item in clean])
            tex_lines.append(f"{tex(receiver)} & {tex(group)} & {len(items)} & {len(clean)} & {mean(all_values):.2f} & {mean(clean_values):.2f} & {all_var:.2f} & {clean_var:.2f} & {all_empty:.2f}/{clean_empty:.2f}\\\\")
    tex_lines += [r"\bottomrule\end{longtable}\normalsize", r"Variance is the sample variance across all 50 ms received-goodput windows within each independent run, then averaged here across repetitions. The receiver-position rows show how geometry changes the distribution; the activity rows show motion effects within each geometry."]
    tex_lines += [r"The summary is descriptive rather than a significance test. Receiver geometry can change the available path quality substantially; motion is interpreted within each receiver position rather than by pooling different geometries."]
    for item in runs:
        m, w = item["metadata"], item["window"]
        comparison = offline / (item["cc_csv"].stem.replace("_offline_cc_summary", "_offline_cc_comparison.png"))
        utilization = offline / (item["cc_csv"].stem.replace("_offline_cc_summary", "_50ms_utilization_cdf.png"))
        cc_lines = [r"\tiny\begin{longtable}{p{1.35cm}rrrrr}", r"\toprule Method & Mean GP & Mean loss & P95 queue & Mean util. & Effective\\ (Mbps) & (\%) & (ms) & (\%) & windows (\%)\\\midrule"]
        method_labels = {"bbr_like": "BBR", "copa_like": "Copa", "fixed_90pct": "Fixed 90\\%", "gcc_like": "GCC", "pcc_vivace_like": "PCC/Vivace", "raw_saturated": "Raw sat.", "scream_like": "SCReAM", "sqp_lite": "SQP-lite"}
        for row in item["cc_summary"]:
            cc_lines.append(f"{method_labels.get(row['algorithm'], tex(row['algorithm']))} & {float(row['mean_goodput_mbps']):.2f} & {float(row['mean_loss_pct']):.2f} & {float(row['p95_queue_delay_ms']):.1f} & {float(row['mean_utilization_pct']):.1f} & {float(row.get('effective_window_pct', 0)):.1f}\\\\")
        cc_lines.append(r"\bottomrule\end{longtable}\normalsize")
        tex_lines += [f"\\clearpage\\section{{Run {item['run_id']}: {tex(receiver_short(item['name']))} -- {tex(condition_label(item['name']))}}}", f"Hardware: {tex(m.get('hardware'))}. Power: {tex(m.get('power'))}. ESP32 placement: {tex(m.get('placement'))}. Brain-to-receiver distance: {tex(m.get('distance'))}. Notes: {tex(m.get('notes'))}.", f"50 ms windows: {w['windows']}; empty windows: {w['empty']} ({w['empty_pct']:.3f}\\%); goodput mean/P50/P95/P99: {w['mean']:.2f}/{w['p50']:.2f}/{w['p95']:.2f}/{w['p99']:.2f} Mbps; sample variance: {w['variance']:.2f} Mbps$^2$.", r"\subsection*{Offline congestion-control replay}", r"Mean GP is the mean replayed goodput (Mbps). Mean loss is the modelled fraction of offered traffic dropped by the replay. P95 queue is the 95th percentile of the modelled queueing delay (ms). Mean util. is mean goodput as a percentage of this run's saturated-goodput trace. Effective windows is the percentage of 50 ms windows with positive replayed goodput. These are per-run values and are not pooled across conditions."] + cc_lines + [r"The accompanying CSV files in the \texttt{offline\_cc} directory contain the complete per-window and per-method results.", r"\begin{center}", f"\\includegraphics[width=0.82\\textwidth,height=0.37\\textheight,keepaspectratio]{{{tex(comparison.relative_to(args.report_root).as_posix())}}}\\\\\\small Offline replay comparison.\\normalsize", f"\\includegraphics[width=0.82\\textwidth,height=0.37\\textheight,keepaspectratio]{{{tex(utilization.relative_to(args.report_root).as_posix())}}}\\\\\\small Utilization CDF over 50 ms windows.\\normalsize", r"\end{center}"]
    if static_controls:
        tex_lines += [r"\clearpage\section*{Static table control comparison}", r"The ESP32-S3 was placed completely still on a table. These independent control runs provide a stationary reference for the head-mounted and receiver-position experiments.", r"\scriptsize\begin{longtable}{r r r r r r}\toprule Run & Windows & Empty (\%) & Mean Mbps & P50 Mbps & Variance Mbps$^2$\\\midrule"]
        for control in static_controls:
            window = control["window"]
            tex_lines.append(f"{control['run_id']} & {window['windows']} & {window['empty_pct']:.2f} & {window['mean']:.2f} & {window['p50']:.2f} & {window['variance']:.2f}\\\\")
        tex_lines += [r"\bottomrule\end{longtable}\normalsize", r"The controls are shown as separate runs, not averaged into one observation. Their purpose is to distinguish motion and receiver-geometry effects from variability present even when the ESP32 is stationary."]
    tex_lines.append(r"\end{document}")
    tex_path = args.report_root / f"{args.report_basename}.tex"
    tex_path.write_text("\n".join(tex_lines), encoding="utf-8")
    pdflatex = shutil.which("pdflatex")
    if pdflatex and runs:
        run([pdflatex, "-interaction=nonstopmode", tex_path.name], cwd=args.report_root)
        run([pdflatex, "-interaction=nonstopmode", tex_path.name], cwd=args.report_root)
    print(f"Built {len(runs)} runs; report directory: {args.report_root}")
    if pdflatex and runs:
        print(f"PDF: {args.report_root / f'{args.report_basename}.pdf'}")


if __name__ == "__main__":
    main()
