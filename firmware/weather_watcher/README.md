# Weather Watcher — Zephyr Firmware

ESP32-E firmware for the weather station. Reads BME280 (temp/humidity/pressure), AS3935 (lightning), and Inspeed WS2R (wind speed) sensors, transmits UDP JSON every 15 minutes via Wi-Fi, then enters deep sleep.

## Prerequisites

- Zephyr RTOS SDK and `west` toolchain installed
- ESP32 toolchain (`xtensa-esp32-elf`)
- Python virtual environment for Zephyr

## Sensor Wiring

| Sensor | ESP32-E Pin |
|---|---|
| BME280 SDA/SCL | GPIO 21 / GPIO 22 |
| AS3935 SDA/SCL | GPIO 21 / GPIO 22 |
| AS3935 IRQ | GPIO 4 |
| WS2R Anemometer | GND / GPIO 27 |

## Build & Flash

1. Set your Wi-Fi credentials in `src/main.c` (`WIFI_SSID` / `WIFI_PASS`)
2. Verify static IP (`CONFIG_NET_CONFIG_MY_IPV4_ADDR` in `prj.conf`) and server IP (`SERVER_IP` in `main.c`)
3. Build and flash:

```bash
source ~/zephyrproject/.venv/bin/activate
cd ~/zephyrproject/apps/weather_watcher
west build -b esp32 -p always
west flash
```

The ESP32 will wake every 15 minutes, read sensors, transmit to `192.168.0.200:5000`, and return to deep sleep.

## Power

Targets ~10µA in deep sleep. With a 3500mAh 18650, expects 1.5–2 years of runtime.
