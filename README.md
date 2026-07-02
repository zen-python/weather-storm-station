# Weather & Storm Prediction Station

Autonomous ultra-low-power weather station powered by ESP32-E with Zephyr RTOS.

## Structure

- `firmware/weather_watcher/` — Zephyr RTOS source for ESP32-E (BME280, AS3935, WS2R anemometer)
- `backend/` — Docker Compose stack (Telegraf, InfluxDB v2, Grafana)

## Quick Start

**Firmware:** See `firmware/weather_watcher/README.md` for build/flash instructions.

**Backend:** On your ARM64 Ubuntu server (`192.168.0.200`):

```bash
cd backend
# Edit telegraf.conf with your Pushover tokens and InfluxDB credentials
docker compose up -d
```

- InfluxDB UI: http://192.168.0.200:8086
- Grafana UI: http://192.168.0.200:3000 (default admin/admin)
