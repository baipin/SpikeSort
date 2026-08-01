# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-01T02:21:41.142899+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/TCP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is whether the wireless link can sustain the configured stream rate while keeping application frame loss, parser errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 10 minutes |
| Capture start UTC | 2026-08-01T01:49:35.960486+00:00 |
| Capture end UTC | 2026-08-01T01:59:35.920548+00:00 |
| Captured frames | 11958 |
| Capture duration | 599.96 s |
| Mean FPS | 20.00 |
| FPS range | 18.65 - 20.91 |
| Mean throughput | 80.27 KiB/s |
| Throughput range | 74.87 - 83.94 KiB/s |
| Total missing frames by sequence | 1 |
| Missing frames by in-window gaps | 1 |
| Longest consecutive missing run | 1 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 51.490 ms |
| Max arrival jitter | 102.580 ms |
| Mean bandwidth volatility | 2.062 KiB/s |
| Max bandwidth volatility | 4.976 KiB/s |
| Latency samples | 11958 |
| Mean latency | 1038.010 ms |
| P50 latency | 1022.045 ms |
| P95 latency | 1166.088 ms |
| P99 latency | 1214.013 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | PASS | 0.0000% | max loss <= 0.1% |
| Mean frame rate | PASS | 20.00 | mean fps >= 95% target |
| Mean throughput | PASS | 80.27 KiB/s | mean throughput >= 95% target |
| Latency availability | PASS | 11958 | SNTP latency samples present |

## Interpretation Notes

- A healthy run should keep loss rate and CRC/resync errors at zero for the current 20 fps x 4 KiB workload.
- Arrival jitter captures WiFi/TCP cadence variability even when TCP eventually delivers every byte.
- Latency is available only when the ESP32-S3 SNTP clock sync succeeds and the laptop clock is also synchronized.
- If latency is unavailable, use throughput, frame cadence, and jitter for link stability, then repeat the run with working NTP before drawing latency conclusions.
- Treat the quality gates as screening checks. A WARN does not automatically invalidate the run, but it should be explained in the experiment notes.

## Experiment Manifest

```json
{
  "experiment_id": "baseline-near-001",
  "operator": "",
  "started_at_local": "",
  "condition_label": "baseline-near",
  "application_context": {
    "workload": "spike_stream_surrogate",
    "downstream_task": "wireless bandwidth and latency validation for neural recording / spike-sorting pipeline",
    "notes": "Baseline close-range hotspot run for checking whether the 20 fps x 4 KiB stream is stable before distance/interference experiments."
  },
  "device": {
    "board": "ESP32-S3-PICO-1",
    "firmware_project": "esp32s3-bandwidth-sender",
    "serial_port": "COM7"
  },
  "network": {
    "ssid": "Dennis",
    "receiver_ip": "192.168.137.1",
    "receiver_port": 5001,
    "hotspot_device": "Windows laptop mobile hotspot",
    "ntp_server": "pool.ntp.org"
  },
  "stream": {
    "transport": "WiFi + TCP",
    "target_fps": 20,
    "payload_bytes": 4096,
    "frame_bytes": 4110
  },
  "condition": {
    "distance_m": 1,
    "line_of_sight": true,
    "board_orientation": "near laptop hotspot",
    "interference_notes": "",
    "laptop_power_mode": "",
    "duration_min": 30
  },
  "neural_data_scenario": {
    "source_notebook_or_dataset": "deterministic firmware surrogate payload",
    "compression_ratio": null,
    "channels_or_neurons": null,
    "sample_rate_hz": null,
    "payload_mapping_notes": "Use this baseline before mapping payload size to a compressed neural stream scenario."
  }
}
```
