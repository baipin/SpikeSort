# ESP32-S3 Neural Stream Bandwidth Experiment Report

Generated at: `2026-07-31T22:03:14.093590+00:00`

## Experiment Context

This report summarizes an ESP32-S3 WiFi/TCP stream used as a neural-data surrogate for downstream spike-sorting and compression experiments. The main engineering question is whether the wireless link can sustain the configured stream rate while keeping application frame loss, parser errors, jitter, and end-to-end latency within an acceptable range.

## Key Results

| Metric | Value |
| --- | ---: |
| Time filter | last 10 minutes |
| Captured frames | 11525 |
| Capture duration | 599.89 s |
| Mean FPS | 19.97 |
| FPS range | 6.74 - 21.83 |
| Mean throughput | 80.14 KiB/s |
| Throughput range | 27.05 - 87.62 KiB/s |
| Total missing frames by sequence | 11 |
| Window missing-frame sum | 0 |
| Mean loss rate | 0.0000% |
| Max loss rate | 0.0000% |
| CRC/resync errors | 0 |
| Old/duplicate frames | 0 |
| Mean arrival jitter | 53.481 ms |
| Max arrival jitter | 589.556 ms |
| Mean bandwidth volatility | 2.083 KiB/s |
| Max bandwidth volatility | 14.830 KiB/s |
| Latency samples | 11525 |
| Mean latency | 1078.437 ms |
| P50 latency | 1056.330 ms |
| P95 latency | 1210.133 ms |
| P99 latency | 1295.045 ms |

## Interpretation Notes

- A healthy run should keep loss rate and CRC/resync errors at zero for the current 20 fps x 4 KiB workload.
- Arrival jitter captures WiFi/TCP cadence variability even when TCP eventually delivers every byte.
- Latency is available only when the ESP32-S3 SNTP clock sync succeeds and the laptop clock is also synchronized.
- If latency is unavailable, use throughput, frame cadence, and jitter for link stability, then repeat the run with working NTP before drawing latency conclusions.

## Experiment Manifest

```json
{
  "experiment_id": "esp32s3_hotspot_baseline_001",
  "operator": "",
  "started_at_local": "",
  "application_context": {
    "workload": "spike_stream_surrogate",
    "downstream_task": "wireless bandwidth and latency validation for neural recording / spike-sorting pipeline",
    "notes": "Use this run to judge whether the ESP32-S3 link can sustain compressed neural-data transport without application-layer frame gaps."
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
    "frame_bytes": 4110,
    "timestamp_mode_expected": "epoch_us when SNTP succeeds; monotonic_us fallback otherwise"
  },
  "condition": {
    "distance_m": null,
    "line_of_sight": true,
    "board_orientation": "",
    "interference_notes": "",
    "laptop_power_mode": "",
    "duration_min": 30
  },
  "neural_data_scenario": {
    "source_notebook_or_dataset": "",
    "compression_ratio": null,
    "channels_or_neurons": null,
    "sample_rate_hz": null,
    "payload_mapping_notes": "Current firmware payload is a deterministic surrogate. Fill this section when mapping payload size to a real compressed neural stream."
  }
}
```
