# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-10T15:58:49.161126+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/UDP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is how much packetized throughput the wireless link can sustain while keeping sequence-gap loss, CRC errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 1 minutes |
| Capture start UTC | 2026-08-10T15:57:47.272052+00:00 |
| Capture end UTC | 2026-08-10T15:58:48.271508+00:00 |
| Captured frames | 48435 |
| Capture duration | 61.00 s |
| Transport | udp |
| Payload bytes | 1024 |
| Frame bytes | 1038 |
| Target FPS | 1000 |
| Target throughput | 1013.67 KiB/s |
| Mean FPS | 792.25 |
| FPS range | 729.50 - 865.92 |
| Mean throughput | 803.08 KiB/s |
| Throughput range | 739.48 - 877.76 KiB/s |
| Total missing frames by sequence | 37 |
| Missing frames by in-window gaps | 37 |
| Longest consecutive missing run | 12 |
| Window missing-frame sum | 37 |
| Mean loss rate | 0.0767% |
| Max loss rate | 1.6010% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 6.423 ms |
| Max arrival jitter | 10.754 ms |
| Mean bandwidth volatility | 25.956 KiB/s |
| Max bandwidth volatility | 30.824 KiB/s |
| Latency samples | 0 |
| Mean latency | n/a |
| P50 latency | n/a |
| P95 latency | n/a |
| P99 latency | n/a |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | WARN | 1.6010% | max loss <= 0.1% |
| Mean frame rate | WARN | 792.25 | mean fps >= 95% target |
| Mean throughput | WARN | 803.08 KiB/s | mean throughput >= 95% target |
| Latency availability | WARN | 0 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260810 235849](figures/bandwidth_timeseries_20260810_235849.png)


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
    "notes": "Use this point to test whether the ESP32-S3 can sustain approximately 1 MiB/s UDP delivery over the laptop hotspot."
  },
  "condition": {
    "duration_min": 10,
    "purpose": "near-1MiB/s UDP throughput point"
  },
  "condition_label": "udp-1k-1000fps",
  "experiment_id": "udp-1k-1000fps-001",
  "frame_bytes": 1038,
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot"
  },
  "operator": "",
  "payload_bytes": 1024,
  "receiver_started_at_local": "2026-08-10T23:57:23",
  "started_at_local": "",
  "stream": {
    "transport": "WiFi + UDP",
    "target_fps": 1000,
    "payload_bytes": 1024,
    "frame_bytes": 1038,
    "nominal_rate_kib_s": 1013.67
  },
  "target_fps": 1000,
  "transport": "udp",
  "udp_socket_rcvbuf": 4194304
}
```
