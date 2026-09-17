# LAN Field Experiment Terminal

This folder contains a small local-network control terminal for the telemetry-enabled saturated UDP experiments.
It uses only Python's standard library, so no web framework or Node.js installation is required.

## How It Works

`server.py` starts an HTTP server on `0.0.0.0:8765`. It serves `index.html`,
the copied floor plan image, marker state, and a small JSON API. The browser is
the operator interface; the Python process remains the owner of the receiver
subprocess and experiment files.

When the operator presses **Start experiment**, the server:

1. Validates and bounds the requested duration to 1--3600 seconds.
2. Creates a new directory below `captures/udp_battery_position_series_20260901/`.
3. Starts the fixed telemetry-enabled `udp_receiver.py` profile.
4. Keeps a 15-second arming period so the detached ESP32 can be powered by a
   power bank and reset.
5. Starts the countdown only after the receiver has parsed and stored its first
   valid UDP frame (`CAPTURE_STARTED`), not when the button is clicked.
6. Streams receiver output into the browser and calculates the remaining time.
7. Lets the operator stop the receiver explicitly or allows the duration to end.

If no valid packet arrives for five seconds after capture begins, the receiver
prints a `UDP_IDLE` heartbeat every five seconds. This distinguishes a quiet
wireless stream from a frozen webpage; the LAN page displays these messages in
the receiver log.

Every run produces the normal receiver files plus `sender_telemetry_*.csv`.
The terminal does not generate images, reports, analysis CSVs, or report-browser
files. It stores only the raw receiver capture, sender telemetry, packet log,
and run metadata so analysis can be performed later without changing shared
report output. To process an existing run manually, use:

```powershell
python tools\build_saturated_udp_telemetry_report.py <capture-directory>
```

## Start

Run this command from the project root:

```powershell
cd G:\ACADEMIC\esp32s3-bandwidth-sender
python field_terminal\server.py
```

On the receiver computer open:

```text
http://127.0.0.1:8765
```

From another computer on the same LAN, replace the address with the receiver
computer's IPv4 address, for example `http://172.27.168.115:8765`.

## Per-run Metadata and Map Markers

Choose `ESP32 sender`, `Receiver computer`, or `Router / hotspot`, then click
the floor plan. Each marker is stored as a normalized `(x, y)` coordinate in
`markers.json`, so it remains correctly positioned when the image is resized.
Click an existing marker to remove it. When **Start experiment** is pressed,
the current markers are copied into that run's `field_metadata.json`; later
marker edits do not change historical runs. The same file stores the hardware,
power source, ESP32 placement, distance, duration, condition, and operator
note entered for that run.

## Operator Procedure

1. Connect the ESP32 by USB and flash the telemetry firmware once.
2. Start this terminal on the receiver computer.
3. Set the condition name, hardware, power source, ESP32 placement, distance,
   duration, and notes. Verify all three map markers.
4. Press **Start experiment**.
5. During the arming message, disconnect USB, connect the power bank, place the
   ESP32, and press **Reset**.
6. Leave the page open to monitor the receiver and remaining time.
7. When finished, reconnect USB only after the capture has stopped if serial
    inspection is needed.

The **Capture result** panel defaults to the newest completed run. Use its
**Completed run** selector to inspect the same summary for any completed run
in any dataset without moving, editing, or regenerating the stored capture.

Each position is a separate capture directory inside the selected dataset.
The current series is stored under
`captures/udp_battery_position_series_20260901/dataset1/`. Change the
condition label for every run (for example `left-posterior-2p5m-rep1`) so
repeated distances remain separate in the later unified report.

## Dataset Management

The Dataset control at the top of the operator panel selects the destination
for new experiments. Use **New** to create another dataset. The run list below
the selector shows the experiments currently bound to that dataset; when more
than one dataset exists, each run has a **Move to ...** button. Moving a run
relocates its complete capture directory, including packet logs, telemetry,
metadata, and figures. The report builder searches dataset folders recursively,
so reports can be generated from the series root without manually editing paths.
Each run also has an **Import** button. It loads that run's condition, hardware,
power, placement, distance, duration, and notes into the form for reuse. Map
markers are left unchanged and are snapshotted independently when the new run
starts.

## Deleting an Invalid Run

The terminal creates a `Delete latest run` control in the operator panel. It is
disabled only by policy, not by a hidden shell command: the server refuses to
delete while a receiver is active, selects only the newest directory below
`captures/udp_battery_position_series_20260901/`, and removes report files
whose names contain that run timestamp. The optional `also delete telemetry
build` checkbox removes only `build_artifacts/telemetry_validation/`. It never
deletes files outside these explicitly approved locations.

## Safety and Scope

The API exposes only start, stop, status, and marker operations. It does not
accept arbitrary shell commands. There is currently no login or encryption, so
use it only on a trusted private LAN. The Codex conversation cannot be embedded
or proxied into this page; the receiver log is provided as the local substitute.
