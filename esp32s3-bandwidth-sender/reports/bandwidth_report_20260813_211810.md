# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-13T13:18:10.177223+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/UDP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is how much packetized throughput the wireless link can sustain while keeping sequence-gap loss, CRC errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | all data |
| Capture start UTC | 2026-08-13T13:13:09.863278+00:00 |
| Capture end UTC | 2026-08-13T13:18:09.590484+00:00 |
| Captured frames | 206800 |
| Capture duration | 299.73 s |
| Transport | udp |
| Payload bytes | 1024 |
| Frame bytes | 1038 |
| Target FPS | unlimited |
| Target throughput | n/a |
| Mean FPS | 690.01 |
| FPS range | 507.42 - 1050.70 |
| Mean throughput | 699.45 KiB/s |
| Throughput range | 514.36 - 1065.06 KiB/s |
| Total missing frames by sequence | 572 |
| Missing frames by in-window gaps | 572 |
| Longest consecutive missing run | 43 |
| Window missing-frame sum | 69658 |
| Mean loss rate | 25.0386% |
| Max loss rate | 35.8685% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 69114 |
| Mean arrival jitter | 7.201 ms |
| Max arrival jitter | 12.647 ms |
| Mean bandwidth volatility | 31.197 KiB/s |
| Max bandwidth volatility | 173.397 KiB/s |
| Latency samples | 206800 |
| Mean latency | 452.661 ms |
| P50 latency | 382.216 ms |
| P95 latency | 635.185 ms |
| P99 latency | 1690.130 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | WARN | 35.8685% | max loss <= 0.1% |
| Latency availability | PASS | 206800 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260813 211810](figures/bandwidth_timeseries_20260813_211810.png)

![Latency Histogram 20260813 211810](figures/latency_histogram_20260813_211810.png)


## Interpretation Notes

- A healthy UDP run should keep loss rate and CRC/resync errors at zero for the current unlimited fps x 1024 byte workload.
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
    "notes": "The ESP32-S3 sender disables FPS pacing and sends numbered 1 KiB UDP datagrams as fast as the socket path allows."
  },
  "condition": {
    "duration_min": 2,
    "purpose": "unpaced UDP maximum-throughput measurement with per-packet sequence logging"
  },
  "condition_label": "udp-max-throughput",
  "experiment_id": "udp-max-throughput-001",
  "frame_bytes": 1038,
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot"
  },
  "operator": "",
  "operator_notes": "Hardware: ESP32-WROOM-32E; Power: Type-C; Placement: in front of the device; Distance: near (<1 m); WiFi: 51*504 router; Receiver IP: 192.168.0.103",
  "payload_bytes": 1024,
  "receiver_started_at_local": "2026-08-13T21:13:09",
  "started_at_local": "",
  "stream": {
    "transport": "WiFi + UDP",
    "target_fps": "unlimited",
    "payload_bytes": 1024,
    "frame_bytes": 1038,
    "nominal_rate_kib_s": null,
    "pacing": "disabled"
  },
  "target_fps": "unlimited",
  "transport": "udp",
  "udp_socket_rcvbuf": 4194304
}
```
