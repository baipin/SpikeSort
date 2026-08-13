# Battery ESP32 UDP Field-Test Workflow

This document describes how to deploy the UDP maximum-throughput firmware to a battery-powered ESP32-S3 and run distance/environment tests after disconnecting USB.

## Purpose

The goal is to measure how the battery-powered ESP32-S3 performs as a WiFi UDP sender under different physical conditions, such as near range, longer distance, obstruction, and movement. The laptop acts as the WiFi hotspot and UDP receiver.

## Current Firmware Settings

The UDP maximum-throughput defaults are stored in:

```text
sdkconfig.defaults.udp_max_throughput
```

Current settings:

```text
SSID: Dennis
Password: 60763312
Receiver IP: 192.168.137.1
Receiver UDP port: 5001
Transport: UDP
Payload: 1024 bytes
Pacing: disabled / maximum throughput
SNTP: required before streaming
```

USB is required only for flashing and serial debugging. After the firmware is flashed, the board can be powered from battery and will automatically reconnect to the hotspot and send UDP packets.

## Laptop Preparation

Before each test:

```text
1. Turn VPN off.
2. Turn Windows Mobile Hotspot on.
3. Confirm the hotspot SSID is Dennis.
4. Confirm the hotspot password is 60763312.
5. Confirm the hotspot adapter IP is 192.168.137.1.
```

Check the laptop IP:

```powershell
Get-NetIPAddress -AddressFamily IPv4
```

## Flash The Battery ESP32-S3

Connect the battery ESP32-S3 to the laptop with USB.

From an ESP-IDF PowerShell terminal:

```powershell
cd G:\ACADEMIC\esp32s3-bandwidth-sender
idf.py set-target esp32s3
idf.py -B build_udp_max_throughput -DSDKCONFIG_DEFAULTS=sdkconfig.defaults.udp_max_throughput build flash monitor
```

Expected serial log signs:

```text
WiFi connected
SNTP synchronized
transport=udp
mode=unlimited
timestamp=epoch_us
```

After this succeeds, stop the serial monitor, disconnect USB, switch to battery power, and press reset/power on the ESP32-S3. The board should run the same UDP sender without USB.

## Run One Environment Test

Use a descriptive condition name, for example:

```text
battery-near
battery-3m-line-of-sight
battery-5m-line-of-sight
battery-behind-wall
battery-moving
battery-low-battery
```

Recommended manual order:

```text
1. Put the ESP32-S3 in the target condition.
2. Start the receiver on the laptop.
3. Press reset/power on the ESP32-S3 immediately after the receiver starts.
4. Wait until the receiver prints UDP metrics.
5. Let the receiver finish automatically.
6. Generate reports and figures.
```

The helper script below performs the receiver run, standard report generation, packet-log visualization, and local report-browser refresh.

Example 5-minute test:

```powershell
cd G:\ACADEMIC\esp32s3-bandwidth-sender

python -u tools\run_udp_field_test.py --condition battery-3m-line-of-sight --duration-s 300
```

If the receiver finishes but the terminal does not show report or image paths, generate the complete report package from the newest capture with:

```powershell
python tools\generate_latest_udp_report.py
```

This single command creates the Markdown report, CSV summary, standard report figures, packet-log figures, and refreshes `reports\index.html` data.

Open the local report browser:

```text
reports\index.html
```

The helper writes raw captures under:

```text
captures\udp_CONDITION_YYYYMMDD_HHMMSS\
```

It writes standard reports under:

```text
reports\
```

## What To Record For Each Environment

Record these notes manually in the lab notebook or experiment notes:

```text
condition name
distance from laptop
line of sight or obstruction
board orientation
battery state
whether the board was moving
nearby WiFi interference
whether VPN was off
```

Important metrics:

```text
mean throughput KiB/s
mean FPS
mean loss rate
max loss rate
CRC errors
P50/P95/P99 latency
receiver packet-rate time series
sequence-gap plot
```

## No-USB Operation Checklist

If USB is disconnected, the receiver output is the main proof that the board is alive.

Healthy receiver signs:

```text
Receiving UDP packets from ('192.168.137.x', ...)
udp fps=...
rate=...
missing=...
loss=...
```

If no packets arrive:

```text
1. Check that the board is powered by battery.
2. Press reset/power on the board.
3. Confirm Mobile Hotspot is still on.
4. Confirm laptop hotspot IP is still 192.168.137.1.
5. Confirm VPN is off.
6. Reconnect USB and check serial logs if needed.
```

## Manual Step-By-Step Protocol

Use this protocol when running without Codex assistance.

### Phase 1: Flash Once Over USB

1. Connect the ESP32-S3 to USB.
2. Open an ESP-IDF PowerShell terminal.
3. Run:

```powershell
cd G:\ACADEMIC\esp32s3-bandwidth-sender
idf.py set-target esp32s3
idf.py -B build_udp_max_throughput -DSDKCONFIG_DEFAULTS=sdkconfig.defaults.udp_max_throughput build flash monitor
```

4. Confirm the serial monitor shows WiFi connection and UDP sender startup.
5. Stop the monitor with `Ctrl+]`.

### Phase 2: Switch To Battery

1. Disconnect USB.
2. Turn on battery power.
3. Put the ESP32-S3 in the first test location.
4. Keep the laptop hotspot on.
5. Keep VPN off.

### Phase 3: Run One Test

1. Choose a condition label, for example `battery-near`.
2. Start the automated receiver/report command:

```powershell
python -u tools\run_udp_field_test.py --condition battery-near --duration-s 300
```

3. Immediately press reset/power on the ESP32-S3.
4. Confirm the terminal prints:

```text
Receiving UDP packets from ('192.168.137.x', ...)
udp fps=...
```

5. Wait for the script to finish. It will generate reports and figures automatically.
6. Write down the physical condition in your lab notes.

If step 5 finishes without image paths, run:

```powershell
python tools\generate_latest_udp_report.py
```

### Phase 4: Repeat For Other Conditions

Move the ESP32-S3 and rerun the helper with a new condition:

```powershell
python -u tools\run_udp_field_test.py --condition battery-3m-line-of-sight --duration-s 300
python -u tools\run_udp_field_test.py --condition battery-5m-line-of-sight --duration-s 300
python -u tools\run_udp_field_test.py --condition battery-behind-wall --duration-s 300
python -u tools\run_udp_field_test.py --condition battery-moving --duration-s 300
```

### Phase 5: Review Results

Open:

```text
reports\index.html
```

Compare conditions by:

```text
mean throughput KiB/s
mean FPS
mean loss rate
max loss rate
CRC errors
P95/P99 latency
packet-rate and loss figures
```
