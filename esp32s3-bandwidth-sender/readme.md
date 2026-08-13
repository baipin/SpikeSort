# ESP32-S3 Bandwidth Sender

This project measures whether an ESP32-S3 WiFi/TCP link can sustain a neural-data-like streaming workload for spike-sorting experiments. The current firmware sends 20 frames per second with a 4 KiB payload per frame. The laptop receiver records the stream, writes metrics to InfluxDB, and Grafana displays a professional real-time dashboard.

## Dashboard Quick Start On A Fresh Clone

These steps assume another computer has only cloned this repository.

### 1. Install Required Software

Install:

- Docker Desktop for Windows, macOS, or Linux
- Python 3.11 or newer
- Git

On Windows, Docker Desktop usually requires:

- CPU virtualization enabled in BIOS/UEFI
- WSL2 enabled
- `VirtualMachinePlatform` enabled

If Docker Desktop reports that virtualization is missing even though Task Manager shows virtualization enabled, run PowerShell as Administrator:

```powershell
wsl --install --no-distribution
wsl --update
wsl --set-default-version 2
```

Then restart Windows.

### 2. Start InfluxDB And Grafana

From the cloned project folder:

```powershell
cd esp32s3-bandwidth-sender
docker compose -f docker-compose.monitoring.yml up -d
```

If `docker` is not in `PATH` on Windows, use:

```powershell
& "C:\Program Files\Docker\Docker\resources\bin\docker.exe" compose -f docker-compose.monitoring.yml up -d
```

Check that both containers are running:

```powershell
docker compose -f docker-compose.monitoring.yml ps
```

### 3. Open Grafana

Open:

```text
http://localhost:3000
```

Login:

```text
User: admin
Password: bandwidth-admin-pass
```

Dashboard:

```text
Neural Link Monitoring / ESP32-S3 Neural Stream Bandwidth Monitor
```

Direct URL:

```text
http://localhost:3000/d/esp32s3-neural-bandwidth/esp32-s3-neural-stream-bandwidth-monitor
```

### 4. Verify InfluxDB Write Path

After the monitoring stack is up:

```powershell
python monitoring\write_sample_influx_point.py
```

Expected output:

```text
Sample InfluxDB point written
```

This confirms that Python can write metrics to InfluxDB.

### 5. Prepare The WiFi Link

The ESP32-S3 firmware currently expects:

```text
SSID: (Your Wifi SSID)
Password: (Your Wifi password)
Receiver IP: 192.168.137.1 (Your computer IP address, get it from ipconfig command)
Receiver TCP port: 5001
```

On Windows, enable Mobile Hotspot with the same SSID and password. The hotspot adapter should normally get:

```text
192.168.137.1
```

You can check it with:

```powershell
Get-NetIPAddress -AddressFamily IPv4
```

### 6. Start The Receiver

Run:

```powershell
python -u receiver.py --manifest experiments\baseline_near.json --experiment-id baseline-near-001 --condition baseline-near
```

The receiver listens on:

```text
0.0.0.0:5001
```

It writes:

- CSV captures to `captures/`
- SQLite data to `captures/bandwidth_capture.sqlite3`
- WebSocket metrics to `ws://127.0.0.1:8765`
- InfluxDB metrics to bucket `esp32s3_bandwidth`

When the ESP32-S3 connects successfully, the receiver should print lines similar to:

```text
fps=20.4 rate=81.8 KiB/s missing=0 loss=0.000% crc_errors=0
```

### 7. What To Look For In Grafana

The dashboard is tuned for the spike-sorting/neural-stream context. The key question is whether the wireless link can carry a steady 20 fps stream without corrupting frame boundaries or creating application-layer frame gaps.

Healthy values are approximately:

```text
fps: 19.5 - 20.5
throughput: 78 - 83 KiB/s
loss_rate: 0
crc_errors: 0
```

Important panels:

- `Wireless Neural Stream Throughput vs 20fps x 4KB Target`
- `Frame Cadence Stability`
- `Application Frame Loss`
- `CRC / Resync Errors`
- `Arrival Interval and Jitter`
- `Rolling Bandwidth Volatility`

## Stop The Monitoring Stack

Stop containers while keeping data volumes:

```powershell
docker compose -f docker-compose.monitoring.yml down
```

Stop containers and delete InfluxDB/Grafana stored data:

```powershell
docker compose -f docker-compose.monitoring.yml down -v
```

## Troubleshooting

If Docker says permission is denied for the Docker pipe on Windows, try:

- Make sure Docker Desktop is open and fully started.
- Sign out and sign back in after Docker Desktop installation.
- Run the terminal as Administrator.
- Confirm the user is in the `docker-users` group.

If the ESP32-S3 does not connect:

- Make sure Mobile Hotspot is on.
- Confirm the laptop has `192.168.137.1`.
- Confirm `receiver.py` is running before resetting the board.
- Check the board serial log for WiFi or TCP errors.

If Grafana shows no real data:

- Run `python monitoring\write_sample_influx_point.py`.
- Keep `python -u receiver.py` running.
- Confirm the receiver log shows `InfluxDB output: http://127.0.0.1:8086`.

## Generate An Experiment Report

The SQLite database is cumulative, so report a specific recent window after a run:

```powershell
python tools\generate_report.py --db captures\bandwidth_capture.sqlite3 --out reports --manifest experiments\run_template.json --last-minutes 10
```

This writes a Markdown report and CSV summary under `reports/`.

The report also writes PNG figures under `reports/figures/`.

For UDP field tests, the simplest way to generate or repair the complete report package for the newest run is:

```powershell
python tools\generate_latest_udp_report.py
```

This processes the newest `captures\udp_*` folder and writes:

- Markdown report and CSV summary under `reports\`
- Standard report figures under `reports\figures\`
- Packet-log figures under the capture folder's `figures\`
- A refreshed local report browser index at `reports\report_index.js`

To process a specific capture folder:

```powershell
python tools\generate_latest_udp_report.py --capture-dir captures\udp_wroom-battery-on-head-near-with-head-rotation_20260813_225240
```

## Multi-Condition Experiments

For receiver-side bottleneck emulation:

```powershell
python -u receiver.py --manifest experiments\throttle_60kib.json --experiment-id throttle-60kib-001 --condition throttle-60kib --read-limit-kib-s 60
```

Generate a report after stopping the receiver:

```powershell
python tools\generate_report.py --db captures\bandwidth_capture.sqlite3 --out reports --manifest experiments\throttle_60kib.json --last-minutes 10
```

Compare several generated summaries:

```powershell
python tools\compare_reports.py --summaries reports\bandwidth_summary_*.csv --out reports\comparisons
```

The latest multi-condition short validation is summarized in `STAGE6_EXPERIMENTS_AND_REPORTING.md`. The generated comparison report and figures are under `reports/comparisons/`.

## UDP Packet-Loss Experiments

The firmware can also be built in UDP mode for packet-loss and maximum-throughput sweeps. UDP sends one numbered frame per datagram, and `udp_receiver.py` estimates loss from sequence gaps.

Example receiver command:

```powershell
python -u udp_receiver.py --manifest experiments\udp_1k_250fps.json --experiment-id udp-1k-250fps-001 --condition udp-1k-250fps --payload-bytes 1024 --target-fps 250
```

The matching firmware configuration must use:

```text
CONFIG_BANDWIDTH_TRANSPORT_UDP=y
CONFIG_BANDWIDTH_PAYLOAD_BYTES=1024
CONFIG_BANDWIDTH_FPS=250
```

Build it with a separate build directory, for example:

```powershell
idf.py -B build_udp_1k_250fps -DSDKCONFIG_DEFAULTS=sdkconfig.defaults.udp_1k_250fps build flash monitor
```

See `STAGE6_EXPERIMENTS_AND_REPORTING.md` for the full UDP sweep matrix and reporting commands.

After any UDP receiver run, generate the corresponding report and figures with:

```powershell
python tools\generate_latest_udp_report.py
```

## Visualize UDP Packet Logs

For UDP maximum-throughput experiments, `udp_receiver.py` writes a packet-level CSV log under the matching capture folder. Each row records one received packet with its sequence number and receive timestamp. The visualization helper can turn this raw log into PNG figures:

```powershell
python tools\visualize_packet_log.py captures\udp_max_throughput_20260812_130124\packet_log_20260812_130127.csv --out-dir captures\udp_max_throughput_20260812_130124\figures
```

For the current run, this generates:

```text
captures\udp_max_throughput_20260812_130124\figures\packet_log_20260812_130127_overview.png
captures\udp_max_throughput_20260812_130124\figures\packet_log_20260812_130127_timing.png
captures\udp_max_throughput_20260812_130124\figures\packet_log_20260812_130127_latency.png
```

The overview figure shows received packet rate, received throughput, missing sequence numbers, loss percentage, and sequence progression over time. The timing figure shows packet inter-arrival intervals. The latency figure is generated when the packet log contains usable sender timestamps.

## Browse Reports In HTML

Open `reports/index.html` in a browser to view generated Markdown reports, figures, key metrics, and selected-report comparisons.

The browser uses `reports/report_index.js`, which is refreshed automatically when `tools/generate_report.py` or `tools/compare_reports.py` runs. To refresh it manually:

```powershell
python tools\build_report_browser.py
```
