import time
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from receiver import InfluxWriter


def main():
    writer = InfluxWriter(
        url="http://127.0.0.1:8086",
        org="neural-link-lab",
        bucket="esp32s3_bandwidth",
        token="bandwidth-monitor-token",
        measurement="bandwidth_window",
        enabled=True,
    )
    metrics = {
        "window_end_ns": time.time_ns(),
        "fps": 20.0,
        "rate_kib_s": 80.27,
        "missing_frames": 0,
        "loss_rate": 0.0,
        "crc_errors": 0,
        "old_frames": 0,
        "avg_interval_ms": 50.0,
        "interval_jitter_ms": 0.2,
        "bandwidth_jitter_kib_s": 0.5,
    }
    writer.write_metrics(metrics)
    if writer.failed_writes:
        raise SystemExit(f"InfluxDB write failed: {writer.last_error}")
    print("Sample InfluxDB point written")


if __name__ == "__main__":
    main()
