# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-10T15:42:46.341591+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/UDP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is how much packetized throughput the wireless link can sustain while keeping sequence-gap loss, CRC errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 1 minutes |
| Capture start UTC | 2026-08-10T15:41:44.940507+00:00 |
| Capture end UTC | 2026-08-10T15:42:44.915594+00:00 |
| Captured frames | 47492 |
| Capture duration | 59.98 s |
| Transport | udp |
| Payload bytes | 1024 |
| Frame bytes | 1038 |
| Target FPS | 800 |
| Target throughput | 810.94 KiB/s |
| Mean FPS | 790.73 |
| FPS range | 725.76 - 857.71 |
| Mean throughput | 801.54 KiB/s |
| Throughput range | 735.68 - 869.44 KiB/s |
| Total missing frames by sequence | 208 |
| Missing frames by in-window gaps | 208 |
| Longest consecutive missing run | 38 |
| Window missing-frame sum | 249 |
| Mean loss rate | 0.5005% |
| Max loss rate | 6.6914% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 6.832 ms |
| Max arrival jitter | 9.948 ms |
| Mean bandwidth volatility | 53.856 KiB/s |
| Max bandwidth volatility | 261.803 KiB/s |
| Latency samples | 0 |
| Mean latency | n/a |
| P50 latency | n/a |
| P95 latency | n/a |
| P99 latency | n/a |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | WARN | 6.6914% | max loss <= 0.1% |
| Mean frame rate | PASS | 790.73 | mean fps >= 95% target |
| Mean throughput | PASS | 801.54 KiB/s | mean throughput >= 95% target |
| Latency availability | WARN | 0 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260810 234246](figures/bandwidth_timeseries_20260810_234246.png)


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
  "receiver_started_at_local": "2026-08-10T23:39:59",
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
