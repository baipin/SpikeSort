"""Extract the ESP32 SEND_SUCCESS_EXPORT block from a serial monitor log."""

import argparse
import csv
import re
from pathlib import Path


def extract(monitor_log: Path, output_csv: Path) -> int:
    rows = []
    active = False
    expected = None
    ended = False
    with monitor_log.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip().replace("\x1b[0m", "")
            if "SEND_SUCCESS_EXPORT_BEGIN" in line:
                active = True
                match = re.search(r"count=(\d+)", line)
                expected = int(match.group(1)) if match else None
                continue
            if "SEND_SUCCESS_EXPORT_END" in line:
                active = False
                ended = True
                continue
            if not active or not re.fullmatch(r"\d+,\d+", line):
                continue
            timestamp, seq = line.split(",", 1)
            rows.append({"send_ok_ts_us": int(timestamp), "seq": int(seq)})
    if not ended:
        raise RuntimeError(f"Incomplete sender export: missing SEND_SUCCESS_EXPORT_END in {monitor_log}")
    if expected is not None and len(rows) != expected:
        raise RuntimeError(
            f"Incomplete sender export: header count={expected}, parsed records={len(rows)}"
        )
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["send_ok_ts_us", "seq"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description="Extract sender success records from an ESP32 monitor log")
    parser.add_argument("monitor_log", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    count = extract(args.monitor_log, args.out)
    print(f"Wrote {count} sender-success records to {args.out}")


if __name__ == "__main__":
    main()
