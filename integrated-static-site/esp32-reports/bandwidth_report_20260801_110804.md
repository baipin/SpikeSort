# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-01T03:08:04.067510+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/TCP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is whether the wireless link can sustain the configured stream rate while keeping application frame loss, parser errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 0.8 minutes |
| Capture start UTC | 2026-08-01T03:07:12.227212+00:00 |
| Capture end UTC | 2026-08-01T03:07:55.632924+00:00 |
| Captured frames | 368 |
| Capture duration | 43.41 s |
| Mean FPS | 8.82 |
| FPS range | 8.02 - 9.24 |
| Mean throughput | 35.42 KiB/s |
| Throughput range | 32.20 - 37.07 KiB/s |
| Total missing frames by sequence | 10 |
| Missing frames by in-window gaps | 10 |
| Longest consecutive missing run | 1 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 244.819 ms |
| Max arrival jitter | 467.915 ms |
| Mean bandwidth volatility | 0.651 KiB/s |
| Max bandwidth volatility | 3.447 KiB/s |
| Latency samples | 368 |
| Mean latency | 5329.628 ms |
| P50 latency | 5487.324 ms |
| P95 latency | 6522.090 ms |
| P99 latency | 6705.307 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | PASS | 0.0000% | max loss <= 0.1% |
| Mean frame rate | WARN | 8.82 | mean fps >= 95% target |
| Mean throughput | WARN | 35.42 KiB/s | mean throughput >= 95% target |
| Latency availability | PASS | 368 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260801 110804](figures/bandwidth_timeseries_20260801_110804.png)

![Latency Histogram 20260801 110804](figures/latency_histogram_20260801_110804.png)


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
    "notes": "Receiver read limit is about half of the nominal 80 KiB/s stream target. This is a stress condition intended to force backlog and frame loss."
  },
  "condition": {
    "receiver_read_limit_kib_s": 40,
    "duration_min": 10,
    "purpose": "severe bottleneck below target throughput"
  },
  "condition_label": "throttle-40kib",
  "experiment_id": "throttle-40kib-001",
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot"
  },
  "operator": "",
  "read_limit_kib_s": 40.0,
  "receiver_started_at_local": "2026-08-01T11:07:11",
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
