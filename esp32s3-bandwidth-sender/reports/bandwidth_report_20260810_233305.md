# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-10T15:33:05.405848+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/UDP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is how much packetized throughput the wireless link can sustain while keeping sequence-gap loss, CRC errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 1 minutes |
| Capture start UTC | 2026-08-10T15:32:04.101619+00:00 |
| Capture end UTC | 2026-08-10T15:33:04.101288+00:00 |
| Captured frames | 30033 |
| Capture duration | 60.00 s |
| Transport | udp |
| Payload bytes | 1024 |
| Frame bytes | 1038 |
| Target FPS | 500 |
| Target throughput | 506.84 KiB/s |
| Mean FPS | 500.00 |
| FPS range | 472.97 - 528.07 |
| Mean throughput | 506.84 KiB/s |
| Throughput range | 479.44 - 535.29 KiB/s |
| Total missing frames by sequence | 0 |
| Missing frames by in-window gaps | 0 |
| Longest consecutive missing run | 0 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 30618 |
| Mean arrival jitter | 8.115 ms |
| Max arrival jitter | 11.268 ms |
| Mean bandwidth volatility | 18.992 KiB/s |
| Max bandwidth volatility | 152.345 KiB/s |
| Latency samples | 30546 |
| Mean latency | 4952.843 ms |
| P50 latency | 4928.756 ms |
| P95 latency | 5076.605 ms |
| P99 latency | 5117.278 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | PASS | 0.0000% | max loss <= 0.1% |
| Mean frame rate | PASS | 500.00 | mean fps >= 95% target |
| Mean throughput | PASS | 506.84 KiB/s | mean throughput >= 95% target |
| Latency availability | PASS | 30546 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260810 233305](figures/bandwidth_timeseries_20260810_233305.png)

![Latency Histogram 20260810 233305](figures/latency_histogram_20260810_233305.png)


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
    "notes": "This point pushes ESP32-S3 UDP packet cadence while measuring receiver sequence gaps."
  },
  "condition": {
    "duration_min": 10,
    "purpose": "high UDP throughput point"
  },
  "condition_label": "udp-1k-500fps",
  "experiment_id": "udp-1k-500fps-001",
  "frame_bytes": 1038,
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot"
  },
  "operator": "",
  "payload_bytes": 1024,
  "receiver_started_at_local": "2026-08-10T23:27:43",
  "started_at_local": "",
  "stream": {
    "transport": "WiFi + UDP",
    "target_fps": 500,
    "payload_bytes": 1024,
    "frame_bytes": 1038,
    "nominal_rate_kib_s": 506.84
  },
  "target_fps": 500,
  "transport": "udp",
  "udp_socket_rcvbuf": 4194304
}
```
