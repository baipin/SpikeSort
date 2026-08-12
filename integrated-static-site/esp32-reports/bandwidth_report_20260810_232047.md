# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-10T15:20:47.686236+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/UDP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is how much packetized throughput the wireless link can sustain while keeping sequence-gap loss, CRC errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 2 minutes |
| Capture start UTC | 2026-08-10T15:18:46.228108+00:00 |
| Capture end UTC | 2026-08-10T15:20:46.220856+00:00 |
| Captured frames | 11996 |
| Capture duration | 119.99 s |
| Transport | udp |
| Payload bytes | 1024 |
| Frame bytes | 1038 |
| Target FPS | 100 |
| Target throughput | 101.37 KiB/s |
| Mean FPS | 102.99 |
| FPS range | 0.22 - 541.65 |
| Mean throughput | 104.40 KiB/s |
| Throughput range | 0.22 - 549.05 KiB/s |
| Total missing frames by sequence | 103 |
| Missing frames by in-window gaps | 0 |
| Longest consecutive missing run | 0 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 20.242 ms |
| Max arrival jitter | 33.827 ms |
| Mean bandwidth volatility | 22.756 KiB/s |
| Max bandwidth volatility | 84.504 KiB/s |
| Latency samples | 12099 |
| Mean latency | 5007.199 ms |
| P50 latency | 4887.518 ms |
| P95 latency | 5085.843 ms |
| P99 latency | 8481.112 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | PASS | 0.0000% | max loss <= 0.1% |
| Mean frame rate | PASS | 102.99 | mean fps >= 95% target |
| Mean throughput | PASS | 104.40 KiB/s | mean throughput >= 95% target |
| Latency availability | PASS | 12099 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260810 232047](figures/bandwidth_timeseries_20260810_232047.png)

![Latency Histogram 20260810 232047](figures/latency_histogram_20260810_232047.png)


## Interpretation Notes

- A healthy UDP run should keep sequence-gap loss and CRC errors at zero for the configured 1 KiB datagram workload.
- Arrival jitter captures UDP datagram cadence variability; sequence gaps represent application-visible packet loss rather than TCP backpressure.
- Latency is available only when the ESP32-S3 SNTP clock sync succeeds and the laptop clock is also synchronized.
- If latency is unavailable, use throughput, frame cadence, and jitter for link stability, then repeat the run with working NTP before drawing latency conclusions.
- Treat the quality gates as screening checks. A WARN does not automatically invalidate the run, but it should be explained in the experiment notes.

## Experiment Manifest

```json
{
  "application_context": {
    "workload": "spike_stream_surrogate",
    "downstream_task": "UDP packet-loss baseline for neural stream transport",
    "notes": "Each UDP datagram carries one numbered frame. Use sequence gaps at the receiver to estimate packet loss."
  },
  "condition": {
    "duration_min": 10,
    "purpose": "low-stress UDP packet-loss sanity check"
  },
  "condition_label": "udp-1k-100fps",
  "experiment_id": "udp-1k-100fps-001",
  "frame_bytes": 1038,
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot"
  },
  "operator": "",
  "payload_bytes": 1024,
  "receiver_started_at_local": "2026-08-10T22:18:02",
  "started_at_local": "",
  "stream": {
    "transport": "WiFi + UDP",
    "target_fps": 100,
    "payload_bytes": 1024,
    "frame_bytes": 1038,
    "nominal_rate_kib_s": 101.37
  },
  "target_fps": 100,
  "transport": "udp",
  "udp_socket_rcvbuf": 4194304
}
```
