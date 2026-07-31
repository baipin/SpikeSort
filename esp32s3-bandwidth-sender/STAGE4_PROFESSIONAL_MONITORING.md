# Stage 4 Professional Monitoring

This stage adds a durable monitoring stack for the ESP32-S3 wireless stream experiment:

- InfluxDB stores one-second receiver metrics as time-series data.
- Grafana visualizes throughput, frame cadence, loss, CRC/resync events, arrival jitter, and rolling bandwidth volatility.
- The dashboard is tuned for the current spike-sorting/neural-stream surrogate workload: 20 fps, 4 KiB payload, TCP over the laptop hotspot.

## Start InfluxDB and Grafana

Install Docker Desktop first if `docker --version` is not available on Windows.

```powershell
docker compose -f docker-compose.monitoring.yml up -d
```

Grafana:

- URL: http://localhost:3000
- User: `admin`
- Password: `bandwidth-admin-pass`
- Dashboard folder: `Neural Link Monitoring`
- Dashboard: `ESP32-S3 Neural Stream Bandwidth Monitor`

InfluxDB:

- URL: http://localhost:8086
- Org: `neural-link-lab`
- Bucket: `esp32s3_bandwidth`
- Token: `bandwidth-monitor-token`

## Run Receiver With InfluxDB Output

```powershell
python -u receiver.py
```

The receiver keeps the previous Stage 3 outputs:

- CSV in `captures/`
- SQLite in `captures/bandwidth_capture.sqlite3`
- WebSocket at `ws://127.0.0.1:8765`

It now also writes one InfluxDB point per metrics window.

To test only the InfluxDB write path after the stack is up:

```powershell
python monitoring\write_sample_influx_point.py
```

## Metrics Written to InfluxDB

Measurement: `bandwidth_window`

Tags:

- `device=esp32s3`
- `transport=wifi_tcp`
- `workload=spike_stream_surrogate`
- `payload_bytes=4096`
- `frame_bytes=4110`

Fields:

- `fps`
- `target_fps`
- `rate_kib_s`
- `target_rate_kib_s`
- `missing_frames`
- `loss_rate`
- `crc_errors`
- `old_frames`
- `avg_interval_ms`
- `interval_jitter_ms`
- `bandwidth_jitter_kib_s`

## Why These Panels Matter

For the spike-sorting pipeline context, this dashboard answers a practical question: can a constrained ESP32-S3 wireless link carry a steady neural-data-like stream without adding application-layer frame gaps or bursty timing instability?

The key panels are:

- Throughput vs target: whether the link sustains the stream budget.
- Frame cadence: whether 20 fps is preserved.
- Application frame loss: whether sender-side timeout drops appear at the receiver.
- CRC/resync events: whether TCP stream parsing or partial-frame recovery is clean.
- Arrival interval jitter: whether WiFi/TCP variability may affect downstream real-time processing.
- Rolling bandwidth volatility: whether the link is stable enough for longer recording windows.

## Stop The Stack

```powershell
docker compose -f docker-compose.monitoring.yml down
```

To remove stored InfluxDB/Grafana data too:

```powershell
docker compose -f docker-compose.monitoring.yml down -v
```
