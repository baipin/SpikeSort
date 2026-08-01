# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-08-01T03:00:07.082076+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/TCP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is whether the wireless link can sustain the configured stream rate while keeping application frame loss, parser errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 10 minutes |
| Capture start UTC | 2026-08-01T02:34:40.058763+00:00 |
| Capture end UTC | 2026-08-01T02:44:40.046203+00:00 |
| Captured frames | 11788 |
| Capture duration | 599.99 s |
| Mean FPS | 19.99 |
| FPS range | 17.12 - 21.75 |
| Mean throughput | 80.23 KiB/s |
| Throughput range | 68.72 - 87.30 KiB/s |
| Total missing frames by sequence | 5 |
| Missing frames by in-window gaps | 5 |
| Longest consecutive missing run | 1 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 49.740 ms |
| Max arrival jitter | 81.441 ms |
| Mean bandwidth volatility | 2.006 KiB/s |
| Max bandwidth volatility | 5.203 KiB/s |
| Latency samples | 11788 |
| Mean latency | 1025.202 ms |
| P50 latency | 1013.155 ms |
| P95 latency | 1144.555 ms |
| P99 latency | 1188.156 ms |

## Quality Gates

| Gate | Status | Value | Criterion |
| --- | --- | ---: | --- |
| CRC / parser integrity | PASS | 0 | crc_errors == 0 |
| Application loss | PASS | 0.0000% | max loss <= 0.1% |
| Mean frame rate | PASS | 19.99 | mean fps >= 95% target |
| Mean throughput | PASS | 80.23 KiB/s | mean throughput >= 95% target |
| Latency availability | PASS | 11788 | SNTP latency samples present |

## Figures

![Bandwidth Timeseries 20260801 110007](figures/bandwidth_timeseries_20260801_110007.png)

![Latency Histogram 20260801 110007](figures/latency_histogram_20260801_110007.png)


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
