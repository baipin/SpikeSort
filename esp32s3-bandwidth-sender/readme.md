# ESP32-S3 Bandwidth Sender

This project measures whether an ESP32-S3 Wi-Fi link can sustain a neural-data-like streaming workload for spike-sorting experiments. It supports both TCP and UDP. The current maximum-throughput UDP profile uses unlimited sending with 1472-byte payloads, while paced profiles can reproduce a specified frame rate. The laptop receiver records packet-level data, sender telemetry, and summary metrics; optional InfluxDB/Grafana services provide live monitoring.

## Current Field Workflow

The LAN field terminal is the operator-facing workflow for battery-powered
position and motion experiments. It records raw captures, sender telemetry,
packet logs, and `field_metadata.json` without generating reports during the
run. Reports and figures are generated explicitly afterward.

The current organized series is under:

```text
captures/udp_battery_position_series_20260901/new/
```

The `new_chair`, `new_control`, and `new_rec` groups are included in the
current LaTeX report. See
`reports/udp_battery_position_series_20260901/README.md` for the report
workflow and the generated report directory for the latest PDF and index CSV.

The report distinguishes within-run 50 ms window variance from run-to-run
variance. It preserves all-run results and a second summary after excluding
only the two operator-reviewed interrupted chair runs.

For the independent official ESP-IDF iperf baseline and the resulting UDP optimization notes, see [OFFICIAL_IPERF_BASELINE.md](OFFICIAL_IPERF_BASELINE.md).

## Repository Layout

The generated experiment data is organized by purpose so the project root stays readable:

- `main/`: ESP32 firmware source.
- `components/`: optional ESP-IDF components.
- `experiments/`: experiment manifests used by the receiver and report generator.
- `tools/`: build, capture, visualization, report, and offline-control simulation scripts.
- `monitoring/`: InfluxDB/Grafana support scripts and dashboard provisioning.
- `captures/legacy_root_captures/`: early receiver CSV/SQLite files that were originally written directly under `captures/`.
- `captures/legacy_root_captures/figures/`: figures associated with early root-level captures whose original per-run folders no longer exist.
- `captures/tcp_experiments/`: TCP capture directories and packet logs.
- `captures/udp_experiments/`: UDP tuning, packet-loss, and WROOM/S3 capture directories.
- `captures/saturated_udp_field_20260826/`: the current organized saturated UDP field-test series. This folder is intentionally kept separate and is not mixed with older exploratory data.
- `reports/runs/`: generated per-run Markdown reports, CSV summaries, and their standard figures.
- `reports/udp_matrices/`: UDP sweep matrix CSV summaries.
- `reports/tcp_best_config/`: TCP best-configuration LaTeX/PDF summaries and related CSV outputs.
- `reports/udp_50ms_summary/`: UDP 50 ms window LaTeX/PDF summaries and related CSV outputs.
- `reports/sqp_trace_simulation/`: SQP paper copy and offline trace-simulation LaTeX/PDF report.
- `reports/sqp_offline/`: per-trace offline congestion-control simulation outputs.
- `reports/saturated_udp_field_20260826/`: dedicated CSV, figures, LaTeX, and PDF report for the current field-test series.
- `build_artifacts/`: ESP-IDF build outputs and archived build caches. These are generated files and are not needed for a fresh clone.

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

### 5. Prepare The Wi-Fi Link

The firmware needs the receiver computer's current Wi-Fi IPv4 address:

```text
SSID: (Your Wifi SSID)
Password: (Your Wifi password)
Receiver IP: <the receiver computer's Wi-Fi IPv4 address>
Receiver UDP/TCP port: 5001
```

Do not assume that Windows Mobile Hotspot always uses `192.168.137.1`. Check the active adapter with:

```powershell
Get-NetIPAddress -AddressFamily IPv4
```

For the recommended unlimited UDP build, the IP is inserted automatically during build and flash:

```powershell
python tools\flash_best_udp_auto.py --port COM7
```

The end-to-end standard pipeline performs the same discovery before flashing:

```powershell
python tools\run_best_udp.py --port COM7 --duration-s 60
```

These commands use the active Wi-Fi/WLAN adapter, not a VPN/TAP adapter. If the computer changes networks, rebuild and flash again, or pass `--receiver-ip <address>` explicitly.

### 6. Start The Receiver

Run:

```powershell
python -u receiver.py --manifest experiments\udp_max_throughput.json --experiment-id udp-manual-001 --condition udp-manual
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

When the ESP32-S3 sends successfully, the receiver should print lines similar to:

```text
fps=20.4 rate=81.8 KiB/s missing=0 loss=0.000% crc_errors=0
```

### 7. What To Look For In Grafana

The dashboard is tuned for the spike-sorting/neural-stream context. The key question is whether the wireless link can carry a steady 20 fps stream without corrupting frame boundaries or creating application-layer frame gaps.

For the old 20 fps TCP/4 KiB demonstration profile, healthy values are approximately:

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
- Run `ipconfig` and confirm the receiver's active Wi-Fi/WLAN IPv4 address matches the address embedded by `flash_best_udp_auto.py`.
- Confirm `receiver.py` is running before resetting the board.
- Check the board serial log for Wi-Fi association or UDP target errors.

If Grafana shows no real data:

- Run `python monitoring\write_sample_influx_point.py`.
- Keep `python -u receiver.py` running.
- Confirm the receiver log shows `InfluxDB output: http://127.0.0.1:8086`.

## Generate An Experiment Report

The SQLite database is cumulative, so report a specific recent window after a run:

```powershell
python tools\generate_report.py --db captures\bandwidth_capture.sqlite3 --out reports --manifest experiments\run_template.json --last-minutes 10
```

This writes a Markdown report and CSV summary under `reports/runs/`.

The report also writes PNG figures under `reports/runs/figures/` and copies the same standard figures into the source capture folder's `figures/` directory. This keeps each experiment folder self-contained while preserving the report browser's shared figure index.

For UDP field tests, the simplest way to generate or repair the complete report package for the newest run is:

```powershell
python tools\generate_latest_udp_report.py
```

This recursively processes the newest `captures\**\udp_*` folder and writes:

- Markdown report and CSV summary under `reports\runs\`
- Standard report figures under `reports\runs\figures\`
- Standard report figures and packet-log figures under the capture folder's `figures\`
- A refreshed local report browser index at `reports\report_index.js`

To process a specific capture folder:

```powershell
python tools\generate_latest_udp_report.py --capture-dir captures\udp_experiments\udp_wroom-battery-on-head-near-with-head-rotation_20260813_225240
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
python tools\compare_reports.py --summaries reports\runs\bandwidth_summary_*.csv --out reports\comparisons
```

The latest multi-condition short validation is summarized in `STAGE6_EXPERIMENTS_AND_REPORTING.md`. The generated comparison report and figures are under `reports/comparisons/`.

## Current Best TCP Configuration

The current best TCP configuration is the big-window, batch-4 profile:

```text
build_tcp_1472_1500fps_precise_blocking_big_tcpwin_batch4_nolog
sdkconfig.defaults.tcp_1472_1500fps_precise_blocking_big_tcpwin_batch4_nolog
```

Best-summary artifacts:

- `reports/tcp_best_config/tcp_best_config_summary.tex`
- `reports/tcp_best_config/tcp_best_config_summary.pdf`
- `reports/runs/figures/bandwidth_timeseries_20260819_002658.png`
- `reports/runs/figures/latency_histogram_20260819_002658.png`
- `reports/figures/tcp_bigwin_batch4_defermetrics_1500fps_rerun_20260819_50ms_throughput_trace_distribution.png`

To regenerate the 50 ms throughput trace for the best capture:

```powershell
python tools\plot_window_throughput_trace.py captures\tcp_experiments\tcp_bigwin_batch4_defermetrics_1500fps_rerun_20260819\packet_log_20260819_002525.csv --window-ms 50 --frame-bytes 1486 --out-dir reports\figures --prefix tcp_bigwin_batch4_defermetrics_1500fps_rerun_20260819 --title "TCP 50 ms Throughput Trace and CDF"
```

The best-run summary numbers are:

- mean throughput: 1143.21 KiB/s
- mean FPS: 787.79
- max loss: 0.0000%
- CRC errors: 0
- 50 ms window mean throughput: 8.76 Mbps
- 50 ms window zero-throughput windows: 1.44%

This is the recommended starting point for third parties who only need the most stable TCP profile and the summary report, not the full tuning history.

To reproduce the best TCP profile end-to-end:

```powershell
python tools\run_best_tcp.py --port COM7 --duration-s 60
```

This script builds and flashes `sdkconfig.defaults.tcp_1472_1500fps_precise_blocking_big_tcpwin_batch4_nolog`, runs `receiver.py`, generates the Markdown/CSV report, regenerates the 50 ms throughput trace/CDF, and refreshes the HTML report browser.

Important TCP settings:

- `CONFIG_BANDWIDTH_TRANSPORT_TCP=y`
- `CONFIG_BANDWIDTH_PAYLOAD_BYTES=1472`
- `CONFIG_BANDWIDTH_FPS=1500`
- `CONFIG_BANDWIDTH_PRECISE_PACING=y`
- `CONFIG_BANDWIDTH_TCP_BLOCKING_SEND=y`
- `CONFIG_BANDWIDTH_TCP_BATCH_FRAMES=4`
- `CONFIG_LWIP_TCP_SND_BUF_DEFAULT=32768`
- `CONFIG_LWIP_TCP_WND_DEFAULT=32768`
- `CONFIG_ESP_WIFI_DYNAMIC_TX_BUFFER_NUM=96`

## UDP Packet-Loss And Maximum-Throughput Experiments

The firmware can also be built in UDP mode for packet-loss and maximum-throughput sweeps. UDP sends one numbered frame per datagram. For strict path-loss measurement, enable the sender-success recorder described below; receiver-only sequence gaps remain an online estimate.

The current unlimited-throughput UDP profile is:

```text
s3-dynamic-tx-1472
sdkconfig.defaults.udp_max_throughput_s3_dynamic_tx_1472
```

This profile is intended to measure the available saturated goodput. It does not impose an FPS limit. Each datagram has a 1472-byte payload, which fits below the usual 1500-byte IP MTU after the 20-byte IP and 8-byte UDP headers. The exact measured throughput depends on the AP/hotspot, channel conditions, receiver scheduling, and current receiver IP.

Important maximum-throughput settings include dynamic Wi-Fi TX/RX buffers, lwIP IRAM optimization, disabled Wi-Fi power save, 11g/n mode, and `CONFIG_BANDWIDTH_SOCKET_SNDBUF=0`. The reproducible saturated profile disables 50 ms telemetry and CRC and uses static payload generation to minimize sender overhead. These diagnostic options must be reported when comparing results. Strict send-success measurements use a separate profile with telemetry enabled.

To reproduce the best UDP profile end-to-end:

```powershell
python tools\run_best_udp.py --port COM7 --duration-s 60
```

This script builds and flashes the best UDP defaults, runs `udp_receiver.py`, generates the Markdown/CSV report, generates packet-log figures, and refreshes the HTML report browser.

Important UDP settings:

- `CONFIG_BANDWIDTH_TRANSPORT_UDP=y`
- `CONFIG_BANDWIDTH_PAYLOAD_BYTES=1472`
- `CONFIG_BANDWIDTH_UNLIMITED_SEND=y`
- `CONFIG_BANDWIDTH_50MS_TELEMETRY` is not set in the saturated throughput profile
- `CONFIG_BANDWIDTH_UDP_BLOCKING_FAST_SEND` is not set
- `CONFIG_BANDWIDTH_DIAG_STATIC_PAYLOAD=y`
- `CONFIG_BANDWIDTH_DIAG_DISABLE_CRC=y`
- `CONFIG_BANDWIDTH_WIFI_PS_NONE=y`
- `CONFIG_BANDWIDTH_WIFI_11GN_ONLY=y`
- `CONFIG_ESP_WIFI_DYNAMIC_TX_BUFFER_NUM=96`
- `CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM=16`
- `CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM=64`
- `CONFIG_ESP_WIFI_DYNAMIC_TX_BUFFER_NUM=96`
- `CONFIG_ESP_WIFI_TX_BA_WIN=12`
- `CONFIG_ESP_WIFI_RX_BA_WIN=16`
- `CONFIG_LWIP_UDP_RECVMBOX_SIZE=64`

For a strict sender-success/path-loss measurement, use the separate strict profile described below. The unlimited profile's ordinary receiver loss is based on received sequence numbers and is not a substitute for the strict send-success comparison.

Example paced receiver command:

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
idf.py -B build_artifacts\manual\build_udp_1k_250fps -DSDKCONFIG_DEFAULTS=sdkconfig.defaults.udp_1k_250fps build flash monitor
```

See `STAGE6_EXPERIMENTS_AND_REPORTING.md` for the full UDP sweep matrix and reporting commands.

## Strict UDP Send-Success Loss Measurement

### Sender diagnostics

The sender can now expose additional diagnostic information without changing the configured UDP datagram size or adding per-packet serial logging. With `CONFIG_BANDWIDTH_EXTENDED_TELEMETRY=y` (enabled by default), the first 52 bytes of the existing payload carry a versioned snapshot containing:

- the 50 ms telemetry window and offered/successful/dropped counters;
- cumulative temporary backpressure events and fatal send errors;
- cumulative `EAGAIN`/`EWOULDBLOCK`, `ENOBUFS`, and `ENOMEM` counts;
- the most recent send error number and sender uptime.

The snapshot is carried in the payload that is already being transmitted, so it does not increase frame length, packet rate, or the number of `send()` calls. It replaces payload-pattern bytes only. The receiver writes these fields to `sender_telemetry_*.csv`, `frames_*.csv`, and `packet_log_*.csv` when the extended version marker is present. The sender also prints the counters once per second when `CONFIG_BANDWIDTH_LOG_STATS=y`; this low-rate diagnostic output should be disabled for the most sensitive throughput benchmark.

These counters are snapshots taken while constructing the next frame. They are useful for identifying sender-side pressure, but they do not turn `send()` success into an air-interface timestamp. `send_ok_ts_us` remains the post-success socket-boundary timestamp recorded by the sender-success recorder.

For a measurement that excludes sender-side backpressure from the loss numerator, use a UDP configuration with:

```text
CONFIG_BANDWIDTH_TRANSPORT_UDP=y
CONFIG_BANDWIDTH_UDP_BLOCKING_FAST_SEND=n
CONFIG_BANDWIDTH_RECORD_SEND_SUCCESSES=y
CONFIG_BANDWIDTH_TEST_DURATION_S=<finite duration>
CONFIG_BANDWIDTH_SEND_RECORD_CAPACITY=<at least expected successful packets>
```

The non-blocking sender calls `send(sock, frame, frame_len, MSG_DONTWAIT)`. Temporary `EAGAIN`, `EWOULDBLOCK`, `ENOBUFS`, `ENOMEM`, and `EINTR` errors increment `send_fail_events`, yield, and retry the same sequence number. Only a complete successful datagram advances `seq` and is recorded as `send_ok_ts_us,seq`. A fatal error is logged separately and causes socket recreation without advancing `seq`.

At the finite test end, capture the serial monitor output so it contains the `SEND_SUCCESS_EXPORT_BEGIN` block. Extract and compare the records as follows:

```powershell
python tools\extract_send_success_log.py serial\sender_monitor.txt --out captures\run\sender_success.csv
python tools\analyze_post_send_udp_loss.py `
  --sender-success captures\run\sender_success.csv `
  --packet-log captures\run\packet_log_*.csv `
  --out captures\run\post_send_udp_loss.json `
  --summary-csv captures\run\post_send_udp_loss.csv
```

The resulting `post_send_loss_rate` is computed from the unique sender-success sequence set and the unique receiver sequence intersection:
`(sender_success - received_success) / sender_success`. It measures loss after `send()` returned success up to receiver application delivery. `send_ok_ts_us` is an ESP32 socket-boundary timestamp taken immediately after `send()` returns; it is not an 802.11 air-interface timestamp. True airtime/ACK loss requires a Wi-Fi monitor capture or lower-level driver instrumentation.

After any UDP receiver run, generate the corresponding report and figures with:

```powershell
python tools\generate_latest_udp_report.py
```

## Visualize UDP Packet Logs

For UDP maximum-throughput experiments, `udp_receiver.py` writes a packet-level CSV log under the matching capture folder. Each row records one received packet with its sequence number and receive timestamp. The visualization helper can turn this raw log into PNG figures:

```powershell
python tools\visualize_packet_log.py captures\udp_experiments\udp_max_throughput_20260812_130124\packet_log_20260812_130127.csv --out-dir captures\udp_experiments\udp_max_throughput_20260812_130124\figures
```

For the current run, this generates:

```text
captures\udp_experiments\udp_max_throughput_20260812_130124\figures\packet_log_20260812_130127_overview.png
captures\udp_experiments\udp_max_throughput_20260812_130124\figures\packet_log_20260812_130127_timing.png
captures\udp_experiments\udp_max_throughput_20260812_130124\figures\packet_log_20260812_130127_latency.png
```

The overview figure shows received packet rate, received throughput, missing sequence numbers, loss percentage, and sequence progression over time. The timing figure shows packet inter-arrival intervals. The latency figure is generated when the packet log contains usable sender timestamps.

For current scripts, each new experiment capture folder should contain its own `figures/` directory. For a UDP saturated field trace, this includes:

- `bandwidth_timeseries_*.png` and `latency_histogram_*.png` copied from the standard report generator.
- `packet_log_*_overview.png`, `packet_log_*_timing.png`, and `packet_log_*_latency.png` from packet-log visualization.
- `offline_cc_comparison.png` and `offline_loss_tail.png` for detached saturated UDP traces with offline congestion-control simulation.

## Browse Reports In HTML

Open `reports/index.html` in a browser to view generated Markdown reports, figures, key metrics, and selected-report comparisons.

The browser uses an inline `window.REPORT_INDEX` payload plus `reports/report_index.js`. Both are refreshed automatically when `tools/generate_report.py`, `tools/generate_latest_udp_report.py`, `tools/run_udp_field_test.py`, `tools/run_udp_throughput_matrix.py`, or `tools/compare_reports.py` runs. If `../integrated-static-site/esp32-reports` exists, the same command also copies the reports, figures, comparison assets, and refreshed HTML/JS into that deployable site folder. To refresh it manually:

```powershell
python tools\build_report_browser.py
```
