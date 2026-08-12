# Stage 6 Experiments and Reporting

Stage 6 turns the live monitor into a repeatable experiment workflow.

## Run a Capture

Start the monitoring stack:

```powershell
docker compose -f docker-compose.monitoring.yml up -d
```

Start the receiver:

```powershell
python -u receiver.py --manifest experiments\baseline_near.json --experiment-id baseline-near-001 --condition baseline-near
```

Reset or flash the ESP32-S3 and let the run continue for the planned duration. For baseline stability, use at least 30 minutes.

## Record the Experiment Condition

Copy `experiments/run_template.json` to a run-specific JSON file and fill in:

- distance and line-of-sight condition
- board orientation
- hotspot device and power mode
- interference notes
- duration
- neural-data mapping notes, such as compression ratio and channel/neuron count

The manifest keeps the bandwidth result connected to the spike-sorting application context instead of becoming an isolated network benchmark.

For a first close-range sanity check, use:

```powershell
experiments\baseline_near.json
```

## Generate the Report

After a run:

```powershell
python tools\generate_report.py --db captures\bandwidth_capture.sqlite3 --out reports --manifest experiments\run_template.json
```

Because `captures/bandwidth_capture.sqlite3` is cumulative, prefer a time filter for routine runs:

```powershell
python tools\generate_report.py --db captures\bandwidth_capture.sqlite3 --out reports --manifest experiments\run_template.json --last-minutes 10
```

Outputs:

- `reports/bandwidth_report_<timestamp>.md`
- `reports/bandwidth_summary_<timestamp>.csv`

The report includes:

- capture duration
- average/min/max throughput
- average/min/max FPS
- missing frames and loss rate
- longest consecutive missing-frame run
- CRC/resync errors
- arrival jitter
- bandwidth volatility
- P50/P95/P99 latency when SNTP-based timestamps are available
- quality gates for CRC integrity, application loss, frame rate, throughput, and latency availability

For the baseline manifest:

```powershell
python tools\generate_report.py --db captures\bandwidth_capture.sqlite3 --out reports --manifest experiments\baseline_near.json --last-minutes 30
```

## Recommended Experiment Matrix

Start with these runs:

| Run | Payload | FPS | Condition | Purpose |
| --- | ---: | ---: | --- | --- |
| baseline-near | 4096 B | 20 | laptop hotspot, board within 1 m | verify clean link and latency baseline |
| throttle-100kib | 4096 B | 20 | receiver read limit 100 KiB/s | verify read-limit instrumentation while staying above target |
| throttle-60kib | 4096 B | 20 | receiver read limit 60 KiB/s | emulate moderate throughput bottleneck below target |
| throttle-40kib | 4096 B | 20 | receiver read limit 40 KiB/s | emulate severe bottleneck and force backlog/drop behavior |
| distance-mid | 4096 B | 20 | 5-10 m | measure WiFi/TCP jitter increase |
| obstructed | 4096 B | 20 | wall or body obstruction | observe loss and backlog behavior |
| long-run | 4096 B | 20 | stable placement, 30+ min | check drift and monitoring durability |

For neural-stream studies, repeat the matrix when payload size changes to represent a new compression ratio or channel count.

## Throughput-Limit Experiments

Windows Mobile Hotspot does not provide a simple reliable per-client WiFi PHY-rate cap. For repeatable bottleneck tests, the receiver supports an artificial TCP read limit:

```powershell
python -u receiver.py --manifest experiments\throttle_60kib.json --experiment-id throttle-60kib-001 --condition throttle-60kib --read-limit-kib-s 60
```

This emulates an end-to-end bottleneck by reading from the TCP socket more slowly. It is not a pure radio-layer cap, but it creates TCP backpressure and is useful for observing frame cadence, sender timeout drops, latency growth, and parser integrity under constrained bandwidth.

Suggested commands:

```powershell
python -u receiver.py --manifest experiments\baseline_near.json --experiment-id baseline-near-001 --condition baseline-near
python -u receiver.py --manifest experiments\throttle_100kib.json --experiment-id throttle-100kib-001 --condition throttle-100kib --read-limit-kib-s 100
python -u receiver.py --manifest experiments\throttle_60kib.json --experiment-id throttle-60kib-001 --condition throttle-60kib --read-limit-kib-s 60
python -u receiver.py --manifest experiments\throttle_40kib.json --experiment-id throttle-40kib-001 --condition throttle-40kib --read-limit-kib-s 40
```

Run only one receiver command at a time. Stop each run with `Ctrl+C`, then generate a report for that run window:

```powershell
python tools\generate_report.py --db captures\bandwidth_capture.sqlite3 --out reports --manifest experiments\throttle_60kib.json --last-minutes 10
```

The report now also writes PNG figures under `reports\figures\`.

## UDP Packet-Loss And Maximum-Throughput Experiments

UDP tests use the same numbered frame format as the TCP sender:

```text
seq_u32 + send_timestamp_u64 + payload + crc16
```

The receiver treats each UDP datagram as one frame. Packet loss is estimated from sequence gaps, while late lower-numbered packets are counted as old/duplicate frames. Unlike TCP, UDP does not retransmit missing datagrams, so these tests expose packet loss directly.

Recommended first sweep:

| Run | Transport | Payload | FPS | Nominal rate | Purpose |
| --- | --- | ---: | ---: | ---: | --- |
| udp-1k-100fps | UDP | 1024 B | 100 | 101.37 KiB/s | sanity check |
| udp-1k-250fps | UDP | 1024 B | 250 | 253.42 KiB/s | moderate throughput |
| udp-1k-500fps | UDP | 1024 B | 500 | 506.84 KiB/s | high throughput |
| udp-1k-800fps | UDP | 1024 B | 800 | 810.94 KiB/s | aggressive throughput search |

Use 1 KiB payload first because it keeps each UDP datagram below common WiFi/Ethernet MTU limits. Testing 4 KiB or 16 KiB UDP datagrams is possible, but it adds IP fragmentation and may measure fragmentation loss rather than only application packet cadence.

For each point, rebuild and flash firmware with UDP enabled and matching payload/FPS. The provided UDP defaults are complete defaults files:

```powershell
sdkconfig.defaults.udp_1k_100fps
sdkconfig.defaults.udp_1k_250fps
sdkconfig.defaults.udp_1k_500fps
sdkconfig.defaults.udp_1k_800fps
```

The active firmware options must include:

```text
CONFIG_BANDWIDTH_TRANSPORT_UDP=y
CONFIG_BANDWIDTH_PAYLOAD_BYTES=1024
CONFIG_BANDWIDTH_FPS=<100|250|500|800>
```

Use a separate build directory so the existing TCP `sdkconfig` does not override the UDP defaults:

```powershell
idf.py -B build_udp_1k_250fps -DSDKCONFIG_DEFAULTS=sdkconfig.defaults.udp_1k_250fps build flash monitor
```

Repeat with the matching defaults file and build directory for each sweep point.

Start the UDP receiver before resetting the board:

```powershell
python -u udp_receiver.py --manifest experiments\udp_1k_250fps.json --experiment-id udp-1k-250fps-001 --condition udp-1k-250fps --payload-bytes 1024 --target-fps 250
```

Suggested receiver commands:

```powershell
python -u udp_receiver.py --manifest experiments\udp_1k_100fps.json --experiment-id udp-1k-100fps-001 --condition udp-1k-100fps --payload-bytes 1024 --target-fps 100
python -u udp_receiver.py --manifest experiments\udp_1k_250fps.json --experiment-id udp-1k-250fps-001 --condition udp-1k-250fps --payload-bytes 1024 --target-fps 250
python -u udp_receiver.py --manifest experiments\udp_1k_500fps.json --experiment-id udp-1k-500fps-001 --condition udp-1k-500fps --payload-bytes 1024 --target-fps 500
python -u udp_receiver.py --manifest experiments\udp_1k_800fps.json --experiment-id udp-1k-800fps-001 --condition udp-1k-800fps --payload-bytes 1024 --target-fps 800
```

After each run, generate a report for the recent window:

```powershell
python tools\generate_report.py --db captures\bandwidth_capture.sqlite3 --out reports --manifest experiments\udp_1k_250fps.json --last-minutes 10
```

Compare all UDP points:

```powershell
python tools\compare_reports.py --summaries reports\bandwidth_summary_<udp100>.csv reports\bandwidth_summary_<udp250>.csv reports\bandwidth_summary_<udp500>.csv reports\bandwidth_summary_<udp800>.csv --out reports\comparisons
```

Choose the maximum-throughput operating point as the highest FPS/rate condition that still has acceptable loss, CRC errors, and P95/P99 latency. For neural-stream use, prefer the fastest point before the loss curve sharply increases, not the absolute highest one-second throughput spike.

## Compare Multiple Conditions

After generating one summary CSV per condition, compare them:

```powershell
python tools\compare_reports.py --summaries reports\bandwidth_summary_*.csv --out reports\comparisons
```

This creates:

- `reports\comparisons\comparison_summary_<timestamp>.csv`
- `reports\comparisons\comparison_report_<timestamp>.md`
- comparison PNG figures for throughput, FPS, loss, latency, and throughput-vs-latency tradeoff

## HTML Report Browser

Open the static browser:

```powershell
reports\index.html
```

It reads `reports\report_index.js` and provides:

- report search and browsing
- rendered report Markdown
- embedded single-run figures
- selected-report comparison tables
- browser-side throughput, FPS, loss, and latency charts

The index is refreshed automatically after `tools\generate_report.py` or `tools\compare_reports.py` writes new outputs. To refresh it manually:

```powershell
python tools\build_report_browser.py
```

## 2026-08-01 Short Validation Runs

Four short receiver-side bottleneck tests were run against the ESP32-S3 on the Windows Mobile Hotspot. Each run was stopped after roughly 45 seconds, so treat these as engineering checks rather than final statistical evidence. For formal reporting, repeat each condition for 10-30 minutes.

| Condition | Receiver read limit | Mean FPS | Mean throughput | Max loss | CRC errors | P95 latency | Note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| baseline-near | none | 19.99 | 80.24 KiB/s | 0.0000% | 0 | 1280.27 ms | Meets the 20 fps x 4 KiB target. |
| throttle-100kib | 100 KiB/s | 17.54 | 70.40 KiB/s | 0.0000% | 0 | 3196.42 ms | TCP backpressure appears even above the nominal stream rate. |
| throttle-60kib | 60 KiB/s | 11.65 | 46.76 KiB/s | 0.0000% | 0 | 4727.93 ms | Moderate bottleneck; latency grows to several seconds. |
| throttle-40kib | 40 KiB/s | 8.82 | 35.42 KiB/s | 0.0000% | 0 | 6522.09 ms | Severe bottleneck; repeated reconnects and high queueing delay. |

Generated outputs:

- `reports\bandwidth_report_20260801_110508.md`
- `reports\bandwidth_report_20260801_110606.md`
- `reports\bandwidth_report_20260801_110704.md`
- `reports\bandwidth_report_20260801_110804.md`
- `reports\comparisons\comparison_report_20260801_110814.md`
- `reports\comparisons\comparison_summary_20260801_110814.png`
- `reports\comparisons\throughput_latency_tradeoff_20260801_110814.png`

Interpretation: the constrained runs preserved parser integrity and delivered every accepted frame without CRC errors, but the effective application throughput fell below the target and end-to-end latency increased sharply. This is consistent with TCP backpressure and receiver-side queueing. The `--read-limit-kib-s` option is therefore useful for repeatable bottleneck studies, but it should be described as application/TCP bottleneck emulation rather than a pure WiFi PHY-rate limit.
