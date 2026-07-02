# Weather Watcher — Zephyr Firmware

ESP32-E firmware for the weather station. Reads BME280 (temp/humidity/pressure), AS3935 (lightning), and Inspeed WS2R (wind speed) sensors, transmits UDP JSON every 15 minutes via Wi-Fi, then enters deep sleep.

## Build (Docker — Recommended)

Uses the official Zephyr Docker image with all toolchains pre-installed.

```bash
# 1. Set your Wi-Fi credentials
vim src/main.c   # change WIFI_SSID / WIFI_PASS

# 2. Pull the image (once, ~3GB)
docker pull ghcr.io/zephyrproject-rtos/zephyr-build:main

# 3. Build
docker run --rm \
  -v "$(pwd):/app" \
  ghcr.io/zephyrproject-rtos/zephyr-build:main \
  west build -b esp32_devkitc/esp32/procpu -p always -d build /app

# 4. Flash (on host, with ESP32 connected via USB)
west flash -d build
```

Or use the convenience script:

```bash
./scripts/docker-build.sh
```

## Build (Local — Advanced)

Requires Zephyr SDK v1.0+, west workspace, and all module dependencies.

See [install-zephyr-sdk.sh](../../scripts/install-zephyr-sdk.sh) for SDK setup.

```bash
source ~/zephyrproject/.venv/bin/activate
cd ~/zephyrproject
west build -b esp32_devkitc/esp32/procpu -p always \
  -d build/weather_watcher apps/weather_watcher
west flash -d build/weather_watcher
```

## Wiring

| Sensor | ESP32-E Pin |
|---|---|
| BME280 SDA/SCL | GPIO 21 / GPIO 22 |
| AS3935 SDA/SCL | GPIO 21 / GPIO 22 |
| AS3935 IRQ | GPIO 4 |
| WS2R Anemometer | GND / GPIO 27 |

See [HARDWARE.md](../../../HARDWARE.md) for the full wiring diagram.

## Configuration

| File | Setting | Default |
|---|---|---|
| `src/main.c` | `WIFI_SSID` | `YOUR_HOME_WIFI_NAME` |
| `src/main.c` | `WIFI_PASS` | `YOUR_WIFI_PASSWORD` |
| `src/main.c` | `SERVER_IP` | `192.168.0.200` |
| `prj.conf` | ESP32 static IP | `192.168.0.199` |
| `prj.conf` | Netmask / Gateway | `255.255.255.0` / `192.168.0.1` |

## Power

Sleep current: ~14 µA. Active: ~75 mA for ~3 s. Runtime: ~1.3 years on a 3500 mAh 18650.
See [power budget](../../../HARDWARE.md#power-budget--battery-life-calculation) for full calculation.
