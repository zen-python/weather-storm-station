# Weather Watcher — Zephyr Firmware

ESP32-E firmware for the weather station. Reads BME280 (temp/humidity/pressure), AS3935 (lightning), and Inspeed WS2R (wind speed) sensors, transmits UDP JSON every 15 minutes via Wi-Fi, then enters deep sleep.

## Prerequisites

- [Zephyr RTOS SDK](https://github.com/zephyrproject-rtos/sdk-ng/releases) (v0.17.0+)
  ```bash
  # Download and install
  wget https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v0.17.0/zephyr-sdk-0.17.0_linux-aarch64_minimal.tar.xz
  tar xf zephyr-sdk-0.17.0_linux-aarch64_minimal.tar.xz -C /opt
  cd /opt/zephyr-sdk-0.17.0
  ./setup.sh -t xtensa-espressif_esp32_zephyr-elf -h
  ```
- Zephyr workspace at `~/zephyrproject` with `west` initialized
- Python virtual environment for Zephyr

## Workspace Setup

Symlink this app into your Zephyr workspace:

```bash
mkdir -p ~/zephyrproject/apps
ln -sf $(pwd) ~/zephyrproject/apps/weather_watcher
```

## Wiring

| Sensor | ESP32-E Pin |
|---|---|
| BME280 SDA/SCL | GPIO 21 / GPIO 22 |
| AS3935 SDA/SCL | GPIO 21 / GPIO 22 |
| AS3935 IRQ | GPIO 4 |
| WS2R Anemometer | GND / GPIO 27 |

See [HARDWARE.md](../../../HARDWARE.md) for the full wiring diagram.

## Build & Flash

1. Set Wi-Fi credentials in `src/main.c` (`WIFI_SSID` / `WIFI_PASS`)
2. Verify static IP (`CONFIG_NET_CONFIG_MY_IPV4_ADDR` in `prj.conf`) and server IP (`SERVER_IP` in `main.c`)
3. Build and flash from the Zephyr workspace root:

```bash
source ~/zephyrproject/.venv/bin/activate
cd ~/zephyrproject
west build -b esp32_devkitc/esp32/procpu -p always -d build/weather_watcher apps/weather_watcher
west flash -d build/weather_watcher
```

The ESP32 will wake every 15 minutes, read sensors, transmit to `192.168.0.200:5000`, and return to deep sleep.

## Power

Sleep current: ~14 µA. Active: ~75 mA for ~3 s. Runtime: ~1.3 years on a 3500 mAh 18650.
See [power budget](../../../HARDWARE.md#power-budget--battery-life-calculation) for full calculation.
