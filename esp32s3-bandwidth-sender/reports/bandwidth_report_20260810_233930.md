# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-10T15:39:30.091289+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/UDP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is how much packetized throughput the wireless link can sustain while keeping sequence-gap loss, CRC errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 1 minutes |
| Capture start UTC | 2026-08-10T15:38:30.006907+00:00 |
| Capture end UTC | 2026-08-10T15:39:29.397546+00:00 |
| Captured frames | 1036 |
| Capture duration | 59.39 s |
| Transport | udp |
| Payload bytes | 1024 |
| Frame bytes | 1038 |
| Target FPS | 800 |
| Target throughput | 810.94 KiB/s |
| Mean FPS | 17.43 |
| FPS range | 15.98 - 19.48 |
| Mean throughput | 17.66 KiB/s |
| Throughput range | 16.20 - 19.75 KiB/s |
| Total missing frames by sequence | 29 |
| Missing frames by in-window gaps | 29 |
| Longest consecutive missing run | 1 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 1071 |
| Mean arrival jitter | 311.791 ms |
| Max arrival jitter | 326.618 ms |
| Mean bandwidth volatility | 0.892 KiB/s |
| Max bandwidth volatility | 1.148 KiB/s |
| Latency samples | 0 |
| Mean latency | n/a |
| P50 latency | n/a |
| P95 latency | n/a |
| P99 latency | n/a |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | PASS | 0.0000% | max loss <= 0.1% |
| Mean frame rate | WARN | 17.43 | mean fps >= 95% target |
| Mean throughput | WARN | 17.66 KiB/s | mean throughput >= 95% target |
| Latency availability | WARN | 0 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260810 233930](figures/bandwidth_timeseries_20260810_233930.png)


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
    "downstream_task": "UDP maximum-throughput search for neural stream transport",
    "notes": "Use this aggressive point to find the onset of packet loss, old packets, or receiver overload."
  },
  "condition": {
    "duration_min": 10,
    "purpose": "aggressive UDP throughput point"
  },
  "condition_label": "udp-1k-800fps",
  "experiment_id": "udp-1k-800fps-001",
  "frame_bytes": 1038,
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot"
  },
  "operator": "",
  "payload_bytes": 1024,
  "receiver_started_at_local": "2026-08-10T23:33:44",
  "started_at_local": "",
  "stream": {
    "transport": "WiFi + UDP",
    "target_fps": 800,
    "payload_bytes": 1024,
    "frame_bytes": 1038,
    "nominal_rate_kib_s": 810.94
  },
  "target_fps": 800,
  "transport": "udp",
  "udp_socket_rcvbuf": 4194304
}
```
