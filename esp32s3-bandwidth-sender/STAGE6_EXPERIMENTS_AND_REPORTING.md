# Stage 6 Experiments and Reporting

Stage 6 turns the live monitor into a repeatable experiment workflow.

## Run a Capture

Start the monitoring stack:

```powershell
docker compose -f docker-compose.monitoring.yml up -d
```

Start the receiver:

```powershell
python -u receiver.py
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

## Recommended Experiment Matrix

Start with these runs:

| Run | Payload | FPS | Condition | Purpose |
| --- | ---: | ---: | --- | --- |
| baseline-near | 4096 B | 20 | laptop hotspot, board within 1 m | verify clean link and latency baseline |
| distance-mid | 4096 B | 20 | 5-10 m | measure WiFi/TCP jitter increase |
| obstructed | 4096 B | 20 | wall or body obstruction | observe loss and backlog behavior |
| long-run | 4096 B | 20 | stable placement, 30+ min | check drift and monitoring durability |

For neural-stream studies, repeat the matrix when payload size changes to represent a new compression ratio or channel count.
