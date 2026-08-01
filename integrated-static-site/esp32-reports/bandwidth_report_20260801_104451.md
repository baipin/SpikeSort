# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-01T02:44:51.484622+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/TCP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is whether the wireless link can sustain the configured stream rate while keeping application frame loss, parser errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 15 minutes |
| Capture start UTC | 2026-08-01T02:29:40.064714+00:00 |
| Capture end UTC | 2026-08-01T02:44:40.046203+00:00 |
| Captured frames | 17746 |
| Capture duration | 899.98 s |
| Mean FPS | 19.99 |
| FPS range | 17.12 - 21.75 |
| Mean throughput | 80.24 KiB/s |
| Throughput range | 68.72 - 87.30 KiB/s |
| Total missing frames by sequence | 6 |
| Missing frames by in-window gaps | 6 |
| Longest consecutive missing run | 1 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 50.113 ms |
| Max arrival jitter | 81.441 ms |
| Mean bandwidth volatility | 2.021 KiB/s |
| Max bandwidth volatility | 5.203 KiB/s |
| Latency samples | 17746 |
| Mean latency | 1025.424 ms |
| P50 latency | 1013.444 ms |
| P95 latency | 1145.201 ms |
| P99 latency | 1188.349 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | PASS | 0.0000% | max loss <= 0.1% |
| Mean frame rate | PASS | 19.99 | mean fps >= 95% target |
| Mean throughput | PASS | 80.24 KiB/s | mean throughput >= 95% target |
| Latency availability | PASS | 17746 | SNTP latency samples present |

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
    "downstream_task": "wireless bandwidth and latency validation for neural recording / spike-sorting pipeline",
    "notes": "Baseline close-range hotspot run for checking whether the 20 fps x 4 KiB stream is stable before distance/interference experiments."
  },
  "condition": {
    "distance_m": 1,
    "line_of_sight": true,
    "board_orientation": "near laptop hotspot",
    "interference_notes": "",
    "laptop_power_mode": "",
    "duration_min": 30
  },
  "condition_label": "baseline-near",
  "device": {
    "board": "ESP32-S3-PICO-1",
    "firmware_project": "esp32s3-bandwidth-sender",
    "serial_port": "COM7"
  },
  "experiment_id": "baseline-near-001",
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot",
    "ntp_server": "pool.ntp.org"
  },
  "neural_data_scenario": {
    "source_notebook_or_dataset": "deterministic firmware surrogate payload",
    "compression_ratio": null,
    "channels_or_neurons": null,
    "sample_rate_hz": null,
    "payload_mapping_notes": "Use this baseline before mapping payload size to a compressed neural stream scenario."
  },
  "operator": "",
  "receiver_started_at_local": "2026-08-01T10:26:28",
  "started_at_local": "",
  "stream": {
    "transport": "WiFi + TCP",
    "target_fps": 20,
    "payload_bytes": 4096,
    "frame_bytes": 4110
  }
}
```
