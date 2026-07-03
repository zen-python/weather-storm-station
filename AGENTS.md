# AGENTS.md

Instructions for AI coding agents working on this repository.

## Project

Autonomous ultra-low-power weather station with storm prediction. ESP32-E reads BME280/AS3935/anemometer sensors, sends UDP JSON every 15 min to an ARM64 Ubuntu server running Telegraf + InfluxDB + Grafana via Docker. Alerts dispatched through Pushover.

## Repo Structure

```
weather/
├── firmware/weather_watcher/   # Zephyr RTOS source (ESP32-E)
│   ├── src/main.c              # Firmware: sensors → UDP → deep sleep
│   ├── prj.conf                # Zephyr Kconfig
│   ├── app.overlay             # Devicetree (I2C, BME280, AS3935)
│   ├── CMakeLists.txt          # Zephyr build
│   └── README.md               # Build/flash instructions
├── backend/                    # Docker Compose stack
│   ├── docker-compose.yml      # InfluxDB 2.7 + Telegraf + Grafana
│   ├── telegraf.conf           # UDP listener, Starlark processor, Pushover output
│   └── grafana/
│       ├── datasources/influxdb.yml
│       └── dashboards/weather.json
├── scripts/
│   ├── docker-build.sh         # Build firmware via Zephyr Docker image
│   └── install-zephyr-sdk.sh   # Local SDK install (advanced)
├── docs/superpowers/
│   ├── specs/                  # Design spec
│   └── plans/                  # Implementation plan
├── HARDWARE.md                 # Wiring diagram, pin map, power budget
└── README.md
```

## Key Conventions

- **Branch**: `master` (single-branch development)
- **Commit style**: conventional commits (`feat:`, `fix:`, `docs:`, `build:`)
- **No comments in code** unless explicitly requested
- **No emojis** unless explicitly requested
- **Token**: `CHANGE_ME_TO_SECURE_TOKEN` is a placeholder — replace with a real InfluxDB token
- **Pushover credentials** in `telegraf.conf` are placeholders

## Network Layout

| Device | IP | Notes |
|---|---|---|
| ESP32-E | `192.168.0.199` | Static IP, no DHCP |
| Ubuntu server | `192.168.0.200` | Docker host, ARM64 |
| Telegraf UDP | port `5000` | ESP32 sends here every 15 min |
| InfluxDB | port `8086` | Internal Docker network |
| Grafana | port `3000` | Internal Docker network |

## Firmware Build

**Docker (recommended):**
```bash
docker pull ghcr.io/zephyrproject-rtos/zephyr-build:main
./scripts/docker-build.sh
```

**Board:** `esp32_devkitc/esp32/procpu`
**SDK:** Zephyr SDK v1.0.1 (xtensa-espressif_esp32_zephyr-elf)

## Backend Deployment

On the ARM64 Ubuntu server:
```bash
cd backend
# Edit telegraf.conf with real tokens
docker compose up -d
```

## Sensor I2C Addresses

| Sensor | Address | Notes |
|---|---|---|
| BME280 | `0x76` | Temp, humidity, pressure |
| AS3935 | `0x03` | Lightning detector, IRQ on GPIO 4 |

## Starlark Alert Logic

The Telegraf Starlark processor in `telegraf.conf` computes:
- `dew_point` — Magnus-Tetens from temp + humidity
- `temp_dew_gap` — air saturation index
- `pressure_trend_3h` — 3-hour rolling window delta
- Three alert conditions: storm (rapid pressure drop), lightning (proximity), rain (pressure + saturation)

## Design Documents

- Spec: `docs/superpowers/specs/2026-07-02-weather-storm-station-design.md`
- Plan: `docs/superpowers/plans/2026-07-02-weather-storm-station-plan.md`

## Known Limitations

- Wind speed GPIO ISR incompatible with deep sleep (needs ESP32 PCNT or RTC GPIO wake)
- Starlark state lost on Telegraf restart (3h pressure history wiped)
- `telegraf.conf` uses `if`/`if`/`if` for alerts (all trigger independently — intentional)
- Grafana dashboard thresholds are approximate; adjust after real data collection
