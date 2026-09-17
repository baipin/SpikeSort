# UDP Battery Position Series

This is the report workspace for the battery-powered, multi-position UDP
experiments started from the LAN field terminal. Raw captures are stored in
`captures/udp_battery_position_series_20260901/`, with one directory per run.
The unified report will preserve every run separately, including repeated
measurements at the same distance.

Run indexing after each batch or after the complete series:

```powershell
python tools\index_battery_position_series.py
```

Each run's `field_metadata.json` is the authoritative record of the ESP32,
router/hotspot, and receiver positions, plus hardware, power, distance,
placement, duration, and notes.

## Published Report Sets

- `chair/`: earlier under-chair runs and their position report.
- `chair_rec_change/`: chair and receiver-location comparison report.
- `new/`: the 2026-09-10 series covering `new_chair`, `new_control`, and
  `new_rec` captures.

The `new` report distinguishes two kinds of variability:

- Within-run variance is calculated across ESP32-send-timestamp-aligned 50 ms
  goodput windows for one capture.
- Run-to-run variance is calculated across the mean goodput values of repeated
  captures in a condition.

The report retains both the all-run aggregate and the aggregate after removing
the two operator-reviewed interrupted runs: chair normal breathing repetition
1 and chair deep breathing repetition 3. The runs remain visible and are
marked `DISCONNECTED/EXCLUDED`; they are not deleted.

Regenerate the current report from the ESP32 project root:

```powershell
python tools\build_battery_position_series_report.py `
  --capture-root captures\udp_battery_position_series_20260901\new `
  --report-root reports\udp_battery_position_series_20260901\new `
  --include-groups new_chair,new_control,new_rec `
  --report-date 2026-09-10 `
  --report-basename new_battery_position_series_report
```

Large `offline_cc/` batches are reproducible and remain local by default. The
curated PDF, LaTeX source, index CSV, and layout figures are suitable for Git.
