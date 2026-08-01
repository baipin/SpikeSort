# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-01T03:06:06.470006+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/TCP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is whether the wireless link can sustain the configured stream rate while keeping application frame loss, parser errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 0.8 minutes |
| Capture start UTC | 2026-08-01T03:05:16.622207+00:00 |
| Capture end UTC | 2026-08-01T03:05:58.132085+00:00 |
| Captured frames | 718 |
| Capture duration | 41.51 s |
| Mean FPS | 17.54 |
| FPS range | 15.44 - 19.52 |
| Mean throughput | 70.40 KiB/s |
| Throughput range | 61.95 - 78.33 KiB/s |
| Total missing frames by sequence | 2 |
| Missing frames by in-window gaps | 2 |
| Longest consecutive missing run | 1 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 153.618 ms |
| Max arrival jitter | 221.084 ms |
| Mean bandwidth volatility | 4.567 KiB/s |
| Max bandwidth volatility | 10.324 KiB/s |
| Latency samples | 718 |
| Mean latency | 2310.255 ms |
| P50 latency | 2388.985 ms |
| P95 latency | 3196.419 ms |
| P99 latency | 3372.561 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | PASS | 0.0000% | max loss <= 0.1% |
| Mean frame rate | WARN | 17.54 | mean fps >= 95% target |
| Mean throughput | WARN | 70.40 KiB/s | mean throughput >= 95% target |
| Latency availability | PASS | 718 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260801 110606](figures/bandwidth_timeseries_20260801_110606.png)

![Latency Histogram 20260801 110606](figures/latency_histogram_20260801_110606.png)


## Interpretation Notes

- A healthy run should keep loss rate and CRC/resync errors at zero for the current 20 fps x 4 KiB workload.
- Arrival jitter captures WiFi/TCP cadence variability even when TCP eventually delivers every byte.
- Latency is available only when the ESP32-S3 SNTP clock sync succeeds and the laptop clock is also synchronized.
- If latency is unavailable, use throughput, frame cadence, and jitter for link stability, then repeat the run with working NTP before drawing latency conclusions.
- Treat the quality gates as screening checks. A WARN does not automatically invalidate the run, but it should be explained in the experiment notes.

## Experiment Manifest

```json
{
  "application_context": {
    "workload": "spike_stream_surrogate",
    "downstream_task": "receiver-side bottleneck emulation for neural stream stability",
    "notes": "Receiver read limit is set above the nominal 80 KiB/s stream target. This should behave close to baseline while verifying the throttling path."
  },
  "condition": {
    "receiver_read_limit_kib_s": 100,
    "duration_min": 10,
    "purpose": "near-baseline control with receiver-side read limiting enabled"
  },
  "condition_label": "throttle-100kib",
  "experiment_id": "throttle-100kib-001",
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot"
  },
  "operator": "",
  "read_limit_kib_s": 100.0,
  "receiver_started_at_local": "2026-08-01T11:05:15",
  "started_at_local": "",
  "stream": {
    "transport": "WiFi + TCP",
    "target_fps": 20,
    "payload_bytes": 4096,
    "frame_bytes": 4110,
    "nominal_rate_kib_s": 80.27
  }
}
```
