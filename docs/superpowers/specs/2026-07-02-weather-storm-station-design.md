# Weather & Storm Prediction Station — Design Spec

**Date:** 2026-07-02
**Status:** Approved

## Overview

Autonomous ultra-low-power weather station that reads environmental sensors (BME280 temperature/humidity/pressure, AS3935 lightning detector, Inspeed WS2R anemometer) on a DFRobot FireBeetle ESP32-E, broadcasts UDP JSON packets every 15 minutes to a local Linux server, which stores time-series data in InfluxDB v2, runs storm prediction via Telegraf Starlark, sends Pushover alerts, and visualizes everything in Grafana.

Target: 1.5–2 year battery life on a single 3500mAh 18650 cell.

## Hardware (Fixed — Not Modified)

| Sensor | ESP32-E Pin | Notes |
|---|---|---|
| BME280 SCL/SDA | GPIO 22 / GPIO 21 | I2C bus, address 0x76 |
| AS3935 SCL/SDA | GPIO 22 / GPIO 21 | Shared I2C bus, address 0x03 |
| AS3935 IRQ | GPIO 4 | Wake-on-strike interrupt |
| WS2R Anemometer | GND / GPIO 27 | Passive pulse counting |

Power: 18650 via JST PH 2.0 battery port through onboard RT9080 LDO.

## Project Structure

```
weather/
├── firmware/
│   └── weather_watcher/
│       ├── src/main.c
│       ├── prj.conf
│       ├── app.overlay
│       └── README.md
├── backend/
│   ├── docker-compose.yml
│   ├── telegraf.conf
│   └── grafana/
│       ├── datasources/influxdb.yml
│       └── dashboards/weather.json
└── README.md
```

## Firmware (Zephyr RTOS)

ESP32-E runs Zephyr RTOS. Source files are written to this repo; the user handles Zephyr SDK/west toolchain installation and flashing.

**Network:**
- Static IP: `192.168.0.199` (no DHCP — skips DHCP lease negotiation for power savings)
- Wi-Fi SSID/password configured in `prj.conf` or `main.c`
- Target server: `192.168.0.200:5000` (UDP)

**Boot cycle (every 15 minutes):**
1. Wake from deep sleep (`PM_STATE_SOFT_OFF`)
2. Configure wind pulse interrupt on GPIO 27 (20ms debounce)
3. Poll BME280 for temp, pressure, humidity
4. On first boot: calibrate AS3935 antenna tuning capacitors
5. Check AS3935 interrupt register for lightning strikes; update count + distance
6. Calculate wind speed from accumulated pulses using Inspeed formula
7. Clear pulse accumulator for next cycle
8. Build JSON payload
9. Wi-Fi handshake (3-second timeout)
10. Send UDP packet
11. Enter deep sleep for 15 minutes

**JSON payload (UDP):**
```json
{"id":"storm_station_01","boot":N,"temp":X.XX,"press":Y.Y,"hum":Z.Z,"wind":W.WW,"lt_count":C,"lt_dist":D}
```

**RTC-retained state across sleep cycles:**
- `boot_sequence` — incrementing counter
- `accumulated_wind_pulses` — wind ticks since last transmission
- `last_wind_pulse_timestamp` — for debounce
- `total_lightning_strikes` — lifetime count
- `last_lightning_distance_km` — most recent strike distance

## Backend (Docker on ARM64 Ubuntu)

All services run on `192.168.0.200` via `docker compose`.

### Services

| Service | Image | Ports | Purpose |
|---|---|---|---|
| influxdb | influxdb:2.7 | 8086 | Time-series storage |
| telegraf | telegraf:latest | 5000/udp | UDP ingestion, Starlark processing, Pushover alerts |
| grafana | grafana:latest | 3000 | Historical dashboards |

### Data Flow

```
ESP32 UDP → Telegraf (port 5000/udp)
                │
                ├── Starlark processor (3h pressure trend, alert logic)
                │
                ├── InfluxDB v2 (all metrics, bucket: "weather")
                │
                └── Pushover HTTPS (alert_trigger=true only)
```

### Starlark Alert Logic

- Maintains a rolling 3-hour (10800 sec) history of pressure readings
- On each incoming metric: computes `pressure_trend_3h = current_press - oldest_press_in_window`
- **Storm alert**: if `pressure_trend_3h <= -3.0` hPa → Pushover notification with message
- **Lightning alert**: if `lt_count > 0` AND `lt_dist <= 15` km → Pushover notification
- Alert metrics are tagged `alert_trigger=true` and routed to Pushover HTTP output only

### Pushover Configuration

- Called via HTTPS POST to `https://pushover.net` with form-encoded body
- Sound: `thunder`, priority: `1`
- User must provide: `PUSHOVER_APP_TOKEN` and `PUSHOVER_USER_KEY` in `telegraf.conf`

## Grafana Dashboards

Single pre-built dashboard `weather.json` with 7 panels:

| Panel | Type | Field(s) |
|---|---|---|
| Temperature (24h) | Time series | `temp` (°C) |
| Humidity (24h) | Time series | `hum` (%) |
| Pressure (24h) | Time series | `press` (hPa) |
| Pressure Trend (3h delta) | Time series | `pressure_trend_3h` |
| Wind Speed (24h) | Time series | `wind` (km/h) |
| Lightning Strikes | Stat + table | `lt_count`, `lt_dist` (km) |
| Storm Alert Log | Table | Tag-filtered `alert_trigger=true` |

Datasource auto-provisioned via `grafana/datasources/influxdb.yml`. Dashboard auto-loaded via Grafana provisioning config.

## Error Handling

**Firmware:**
- Wi-Fi handshake timeout: 3 seconds, then skip transmission and go to sleep
- Sensor readiness check: `device_is_ready()` before polling; if unavailable, fields default to 0/null in JSON
- UDP send failure: silent — no retry to conserve power; data loss is acceptable for a 15-min cycle
- AS3935 calibration failure: logged but not fatal; lightning detection may be suboptimal

**Backend:**
- Telegraf UDP listener: stateless, no backpressure — if InfluxDB or Pushover is down, metrics are dropped for that cycle
- InfluxDB bucket not found: Telegraf output plugin logs error, continues
- Pushover HTTP failure: Telegraf output plugin logs error, no retry

## Out of Scope

- HTTPS/TLS on the ESP32 — UDP is plaintext on the local LAN
- Authentication between ESP32 and Telegraf — trusted LAN model
- OTA firmware updates for ESP32
- Rainfall or UV sensors
- Mobile app — Pushover serves as the notification endpoint
