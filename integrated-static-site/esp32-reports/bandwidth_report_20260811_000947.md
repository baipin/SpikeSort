# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-10T16:09:47.199300+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/UDP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is how much packetized throughput the wireless link can sustain while keeping sequence-gap loss, CRC errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 1 minutes |
| Capture start UTC | 2026-08-10T16:08:46.093313+00:00 |
| Capture end UTC | 2026-08-10T16:09:45.933287+00:00 |
| Captured frames | 44514 |
| Capture duration | 59.84 s |
| Transport | udp |
| Payload bytes | 1024 |
| Frame bytes | 1038 |
| Target FPS | 1200 |
| Target throughput | 1216.41 KiB/s |
| Mean FPS | 741.99 |
| FPS range | 675.03 - 808.40 |
| Mean throughput | 752.14 KiB/s |
| Throughput range | 684.25 - 819.45 KiB/s |
| Total missing frames by sequence | 76 |
| Missing frames by in-window gaps | 76 |
| Longest consecutive missing run | 18 |
| Window missing-frame sum | 76 |
| Mean loss rate | 0.1697% |
| Max loss rate | 2.4226% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 7.025 ms |
| Max arrival jitter | 8.547 ms |
| Mean bandwidth volatility | 26.517 KiB/s |
| Max bandwidth volatility | 35.672 KiB/s |
| Latency samples | 44514 |
| Mean latency | 4705.769 ms |
| P50 latency | 4680.860 ms |
| P95 latency | 4826.340 ms |
| P99 latency | 4874.539 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | WARN | 2.4226% | max loss <= 0.1% |
| Mean frame rate | WARN | 741.99 | mean fps >= 95% target |
| Mean throughput | WARN | 752.14 KiB/s | mean throughput >= 95% target |
| Latency availability | PASS | 44514 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260811 000947](figures/bandwidth_timeseries_20260811_000947.png)

![Latency Histogram 20260811 000947](figures/latency_histogram_20260811_000947.png)


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
    "notes": "Use this overload point to identify the packet-loss slope beyond the stable UDP operating region."
  },
  "condition": {
    "duration_min": 10,
    "purpose": "overload UDP throughput point"
  },
  "condition_label": "udp-1k-1200fps",
  "experiment_id": "udp-1k-1200fps-001",
  "frame_bytes": 1038,
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot"
  },
  "operator": "",
  "payload_bytes": 1024,
  "receiver_started_at_local": "2026-08-11T00:08:05",
  "started_at_local": "",
  "stream": {
    "transport": "WiFi + UDP",
    "target_fps": 1200,
    "payload_bytes": 1024,
    "frame_bytes": 1038,
    "nominal_rate_kib_s": 1216.41
  },
  "target_fps": 1200,
  "transport": "udp",
  "udp_socket_rcvbuf": 4194304
}
```
