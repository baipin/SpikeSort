# Stage 5 Clock Sync and Latency

Stage 5 adds timestamp calibration for end-to-end latency measurement without changing the binary frame size.

## Firmware Behavior

The ESP32-S3 still sends:

```text
[seq: uint32 little-endian][timestamp_us: uint64 little-endian][payload][crc16]
```

After WiFi connects, the firmware tries to synchronize system time using SNTP:

```text
server: pool.ntp.org
timeout: 15000 ms
```

If SNTP succeeds, `timestamp_us` is Unix epoch time in microseconds. The receiver can then estimate:

```text
latency_ms = receiver_epoch_time - sender_epoch_time
```

If SNTP fails, the firmware falls back to `esp_timer_get_time()` monotonic microseconds. Throughput, loss, CRC, cadence, and jitter remain valid, but end-to-end latency is marked unavailable.

## Receiver Behavior

The receiver classifies each timestamp:

- `epoch_us`: trusted wall-clock timestamp, latency is calculated.
- `epoch_untrusted`: timestamp looks like epoch time but the clock skew is too large.
- `monotonic_us`: board uptime timestamp, latency unavailable.

New per-frame fields:

- `timestamp_mode`
- `latency_ms`

New per-window metrics:

- `latency_count`
- `latency_avg_ms`
- `latency_p50_ms`
- `latency_p95_ms`
- `latency_p99_ms`

These fields are written to CSV, SQLite, WebSocket messages, and InfluxDB.

## Validation

Run the receiver:

```powershell
python -u receiver.py
```

Healthy latency-enabled output includes:

```text
latency_p95=...
```

If the log shows:

```text
latency_p95=unavailable
```

then the link metrics are still usable, but the ESP32-S3 did not obtain trusted wall-clock time. Check that the hotspot has internet access and that the laptop clock is synchronized.
