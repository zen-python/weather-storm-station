# Weather & Storm Prediction Station — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full firmware source, backend Docker config, and Grafana dashboard for an autonomous ultra-low-power weather station with storm prediction alerts.

**Architecture:** Monorepo with `firmware/` (Zephyr RTOS source for ESP32-E) and `backend/` (docker-compose for Telegraf + InfluxDB v2 + Grafana on ARM64 Ubuntu). ESP32 reads BME280/AS3935/anemometer sensors, sends UDP JSON every 15 min to Telegraf, which feeds InfluxDB and Pushover alerts. Grafana auto-provisions dashboards.

**Tech Stack:** Zephyr RTOS (ESP32-E firmware), Docker Compose (Telegraf/InfluxDB v2/Grafana), Starlark (alert logic), Pushover (mobile alerts)

---

### Task 1: Initialize repository and directory structure

**Files:**
- Create: `firmware/weather_watcher/src/` (directory)
- Create: `backend/grafana/datasources/` (directory)
- Create: `backend/grafana/dashboards/` (directory)
- Create: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: Create directories**

```bash
mkdir -p firmware/weather_watcher/src backend/grafana/datasources backend/grafana/dashboards
```

- [ ] **Step 2: Initialize git**

```bash
git init
```

- [ ] **Step 3: Write `.gitignore`**

```
# Zephyr build artifacts
firmware/weather_watcher/build/

# Docker volumes
backend/grafana/grafana-data/
backend/influxdb-storage/

# OS files
.DS_Store
Thumbs.db
```

- [ ] **Step 4: Write root `README.md`**

```markdown
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
```

- [ ] **Step 5: Create `.gitkeep` placeholders**

```bash
touch firmware/weather_watcher/src/.gitkeep backend/grafana/datasources/.gitkeep backend/grafana/dashboards/.gitkeep
```

---

### Task 2: Write firmware Kconfig (`prj.conf`)

**Files:**
- Create: `firmware/weather_watcher/prj.conf`

- [ ] **Step 1: Write `prj.conf`**

```
CONFIG_PM=y
CONFIG_PM_DEVICE=y
CONFIG_GPIO=y
CONFIG_I2C=y
CONFIG_SENSOR=y
CONFIG_BME280=y

CONFIG_NET_L2_ETHERNET=n
CONFIG_NET_L2_WIFI_MGMT=y
CONFIG_NET_UDP=y
CONFIG_NET_IPV4=y
CONFIG_NET_SOCKETS=y
CONFIG_NET_SOCKETS_POSIX_NAMES=y

CONFIG_NET_CONFIG_SETTINGS=y
CONFIG_NET_CONFIG_MY_IPV4_ADDR="192.168.0.199"
CONFIG_NET_CONFIG_MY_IPV4_NETMASK="255.255.255.0"
CONFIG_NET_CONFIG_MY_IPV4_GW="192.168.0.1"
```

- [ ] **Step 2: Verify file was created**

```bash
cat firmware/weather_watcher/prj.conf
```

---

### Task 3: Write firmware devicetree overlay (`app.overlay`)

**Files:**
- Create: `firmware/weather_watcher/app.overlay`

- [ ] **Step 1: Write `app.overlay`**

```dts
&i2c0 {
    status = "okay";
    clock-frequency = <I2C_BITRATE_STANDARD>;
    pinctrl-0 = <&i2c0_default>;
    pinctrl-names = "default";

    bme280: bme280@76 {
        compatible = "bosch,bme280";
        reg = <0x76>;
    };

    as3935: as3935@03 {
        compatible = "ams,as3935";
        reg = <0x03>;
        irq-gpios = <&gpio0 4 GPIO_ACTIVE_HIGH>;
        status = "okay";
    };
};

&pinctrl {
    i2c0_default: i2c0_default {
        group1 {
            pinmux = <I2C0_SDA_GPIO21>,
                     <I2C0_SCL_GPIO22>;
            bias-pull-up;
        };
    };
};
```

- [ ] **Step 2: Verify file was created**

```bash
cat firmware/weather_watcher/app.overlay
```

---

### Task 4: Write firmware main application (`main.c`)

**Files:**
- Create: `firmware/weather_watcher/src/main.c`

- [ ] **Step 1: Write `main.c`**

```c
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/net/net_if.h>
#include <zephyr/net/socket.h>
#include <zephyr/net/wifi_mgmt.h>
#include <zephyr/sys/printk.h>
#include <zephyr/pm/pm.h>
#include <esp_sleep.h>
#include <string.h>

#define WIFI_SSID "YOUR_HOME_WIFI_NAME"
#define WIFI_PASS "YOUR_WIFI_PASSWORD"
#define SERVER_IP "192.168.0.200"
#define SERVER_PORT 5000
#define SLEEP_TIME_SEC 900
#define WIND_PIN 27

static RTC_DATA_ATTR uint32_t boot_sequence = 0;
static RTC_DATA_ATTR uint32_t accumulated_wind_pulses = 0;
static RTC_DATA_ATTR int64_t last_wind_pulse_timestamp = 0;
static RTC_DATA_ATTR uint32_t total_lightning_strikes = 0;
static RTC_DATA_ATTR uint32_t last_lightning_distance_km = 0;

static const struct device *const bme280_dev = DEVICE_DT_GET(DT_NODELABEL(bme280));
static const struct device *const i2c_bus = DEVICE_DT_GET(DT_NODELABEL(i2c0));
static const struct gpio_dt_spec wind_gpio = GPIO_DT_SPEC_GET_BY_IDX(DT_NODELABEL(gpio0), WIND_PIN, 0);
static struct gpio_callback wind_cb_data;

void wind_pulse_isr(const struct device *port, struct gpio_callback *cb, gpio_port_pins_t pins) {
    int64_t now = k_uptime_get();
    if ((now - last_wind_pulse_timestamp) > 20) {
        accumulated_wind_pulses++;
        last_wind_pulse_timestamp = now;
    }
}

int calibrate_as3935_antenna(void) {
    uint8_t reg_addr = 0x08;
    uint8_t reg_val = 0x00;

    struct i2c_dt_spec as3935_spec = {
        .bus = i2c_bus,
        .addr = 0x03
    };

    if (i2c_write_read_dt(&as3935_spec, &reg_addr, 1, &reg_val, 1) < 0) {
        printk("AS3935: calibration read failed\n");
        return -1;
    }

    reg_val = (reg_val & 0xF0) | 0x08;

    if (i2c_reg_write_byte_dt(&as3935_spec, 0x08, reg_val) < 0) {
        printk("AS3935: calibration write failed\n");
        return -1;
    }

    return 0;
}

int run_network_handshake(void) {
    struct net_if *iface = net_if_get_default();
    struct wifi_connect_req_params params = {
        .ssid = WIFI_SSID,
        .ssid_length = strlen(WIFI_SSID),
        .psk = WIFI_PASS,
        .psk_length = strlen(WIFI_PASS),
        .channel = WIFI_CHANNEL_ANY,
        .security = WIFI_SECURITY_TYPE_PSK,
    };

    if (net_mgmt(NET_REQUEST_WIFI_CONNECT, iface, &params, sizeof(params))) {
        printk("Wi-Fi connect request failed\n");
        return -1;
    }

    int timeout = 30;
    while (!net_if_is_up(iface)) {
        k_msleep(100);
        if (--timeout <= 0) {
            printk("Wi-Fi handshake timeout\n");
            return -1;
        }
    }

    return 0;
}

int main(void) {
    struct sensor_value temp, press, hum;
    char json_buffer[256];

    boot_sequence++;

    gpio_pin_configure_dt(&wind_gpio, GPIO_INPUT | GPIO_PULL_UP);
    gpio_pin_interrupt_configure_dt(&wind_gpio, GPIO_INT_EDGE_TO_ACTIVE);
    gpio_init_callback(&wind_cb_data, wind_pulse_isr, BIT(wind_gpio.pin));
    gpio_add_callback(wind_gpio.port, &wind_cb_data);

    if (device_is_ready(bme280_dev)) {
        sensor_sample_fetch(bme280_dev);
        sensor_channel_get(bme280_dev, SENSOR_CHAN_AMBIENT_TEMP, &temp);
        sensor_channel_get(bme280_dev, SENSOR_CHAN_PRESS, &press);
        sensor_channel_get(bme280_dev, SENSOR_CHAN_HUMIDITY, &hum);
    }

    if (boot_sequence == 1) {
        calibrate_as3935_antenna();
    }

    struct i2c_dt_spec as3935_spec = {
        .bus = i2c_bus,
        .addr = 0x03
    };

    uint8_t int_reg_addr = 0x03;
    uint8_t int_val = 0x00;

    if (i2c_write_read_dt(&as3935_spec, &int_reg_addr, 1, &int_val, 1) == 0) {
        if ((int_val & 0x08) == 0x08) {
            total_lightning_strikes++;

            uint8_t dist_reg = 0x07;
            uint8_t dist_val = 0x00;
            if (i2c_write_read_dt(&as3935_spec, &dist_reg, 1, &dist_val, 1) == 0) {
                last_lightning_distance_km = dist_val & 0x3F;
            }
        }
    }

    float rps = (float)accumulated_wind_pulses / (float)SLEEP_TIME_SEC;
    float wind_kmh = (rps * 2.5) * 1.60934;
    accumulated_wind_pulses = 0;

    snprintf(json_buffer, sizeof(json_buffer),
             "{\"id\":\"storm_station_01\",\"boot\":%u,\"temp\":%.2f,\"press\":%.1f,\"hum\":%.1f,\"wind\":%.2f,\"lt_count\":%u,\"lt_dist\":%u}",
             boot_sequence,
             sensor_value_to_double(&temp),
             sensor_value_to_double(&press) * 10.0,
             sensor_value_to_double(&hum),
             wind_kmh,
             total_lightning_strikes,
             last_lightning_distance_km);

    if (run_network_handshake() == 0) {
        int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (sock >= 0) {
            struct sockaddr_in srv_addr = {
                .sin_family = AF_INET,
                .sin_port = htons(SERVER_PORT)
            };
            inet_pton(AF_INET, SERVER_IP, &srv_addr.sin_addr);
            sendto(sock, json_buffer, strlen(json_buffer), 0, (struct sockaddr *)&srv_addr, sizeof(srv_addr));
            close(sock);
        }
    }

    esp_sleep_enable_timer_wakeup((uint64_t)SLEEP_TIME_SEC * 1000000);
    pm_state_force(0, &(struct pm_state_info){.state = PM_STATE_SOFT_OFF});
    k_sleep(K_FOREVER);

    return 0;
}
```

- [ ] **Step 2: Verify file was created**

```bash
wc -l firmware/weather_watcher/src/main.c
```

---

### Task 5: Write firmware README

**Files:**
- Create: `firmware/weather_watcher/README.md`

- [ ] **Step 1: Write firmware README**

```markdown
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
```

- [ ] **Step 2: Verify file was created**

```bash
cat firmware/weather_watcher/README.md
```

---

### Task 6: Write backend `docker-compose.yml`

**Files:**
- Create: `backend/docker-compose.yml`

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
version: '3.8'

services:
  influxdb:
    image: influxdb:2.7
    container_name: influxdb_weather
    ports:
      - "8086:8086"
    volumes:
      - influxdb-storage:/var/lib/influxdb2
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD=admin12345
      - DOCKER_INFLUXDB_INIT_ORG=home
      - DOCKER_INFLUXDB_INIT_BUCKET=weather
      - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=CHANGE_ME_TO_SECURE_TOKEN
    restart: always

  telegraf:
    image: telegraf:latest
    container_name: telegraf_ingestion
    ports:
      - "5000:5000/udp"
    volumes:
      - ./telegraf.conf:/etc/telegraf/telegraf.conf:ro
    depends_on:
      - influxdb
    restart: always

  grafana:
    image: grafana/grafana:latest
    container_name: grafana_weather
    ports:
      - "3000:3000"
    volumes:
      - ./grafana/datasources:/etc/grafana/provisioning/datasources:ro
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
      - ./grafana/grafana-dashboards-default.yaml:/etc/grafana/provisioning/dashboards/default.yaml:ro
      - grafana-storage:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - influxdb
    restart: always

volumes:
  influxdb-storage:
  grafana-storage:
```

- [ ] **Step 2: Verify file was created**

```bash
cat backend/docker-compose.yml
```

---

### Task 7: Write Grafana dashboard provisioning config

**Files:**
- Create: `backend/grafana/grafana-dashboards-default.yaml`

- [ ] **Step 1: Write `grafana-dashboards-default.yaml`**

```yaml
apiVersion: 1

providers:
  - name: 'Weather Station'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
```

- [ ] **Step 2: Verify file was created**

```bash
cat backend/grafana/grafana-dashboards-default.yaml
```

---

### Task 8: Write Grafana InfluxDB datasource config

**Files:**
- Create: `backend/grafana/datasources/influxdb.yml`

- [ ] **Step 1: Write `influxdb.yml`**

```yaml
apiVersion: 1

datasources:
  - name: InfluxDB
    type: influxdb
    access: proxy
    url: http://influxdb:8086
    jsonData:
      version: Flux
      organization: home
      defaultBucket: weather
      tlsSkipVerify: true
    secureJsonData:
      token: CHANGE_ME_TO_SECURE_TOKEN
    editable: true
```

- [ ] **Step 2: Verify file was created**

```bash
cat backend/grafana/datasources/influxdb.yml
```

---

### Task 9: Write Grafana dashboard JSON

**Files:**
- Create: `backend/grafana/dashboards/weather.json`

- [ ] **Step 1: Write `weather.json`**

```json
{
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": {"type": "datasource", "uid": "grafana"},
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 0,
  "id": null,
  "links": [],
  "panels": [
    {
      "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
      "fieldConfig": {
        "defaults": {
          "color": {"mode": "palette-classic"},
          "custom": {
            "axisBorderShow": false,
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "°C",
            "axisPlacement": "auto",
            "fillOpacity": 10,
            "gradientMode": "opacity",
            "hideFrom": {"legend": false, "tooltip": false, "viz": false},
            "lineWidth": 2,
            "scaleDistribution": {"type": "linear"},
            "thresholdsStyle": {"mode": "off"}
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {"color": "green", "value": null},
              {"color": "red", "value": 80}
            ]
          },
          "unit": "celsius"
        },
        "overrides": []
      },
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
      "id": 1,
      "options": {
        "legend": {"calcs": ["mean", "min", "max"], "displayMode": "table", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      },
      "targets": [
        {
          "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
          "query": "from(bucket: \"weather\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"weather\")\n  |> filter(fn: (r) => r[\"_field\"] == \"temp\")",
          "refId": "A"
        }
      ],
      "title": "Temperature",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
      "fieldConfig": {
        "defaults": {
          "color": {"mode": "palette-classic"},
          "custom": {
            "axisBorderShow": false,
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "%",
            "axisPlacement": "auto",
            "fillOpacity": 10,
            "gradientMode": "opacity",
            "hideFrom": {"legend": false, "tooltip": false, "viz": false},
            "lineWidth": 2,
            "scaleDistribution": {"type": "linear"},
            "thresholdsStyle": {"mode": "off"}
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {"color": "green", "value": null},
              {"color": "red", "value": 80}
            ]
          },
          "unit": "percent"
        },
        "overrides": []
      },
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0},
      "id": 2,
      "options": {
        "legend": {"calcs": ["mean", "min", "max"], "displayMode": "table", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      },
      "targets": [
        {
          "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
          "query": "from(bucket: \"weather\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"weather\")\n  |> filter(fn: (r) => r[\"_field\"] == \"hum\")",
          "refId": "A"
        }
      ],
      "title": "Humidity",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
      "fieldConfig": {
        "defaults": {
          "color": {"mode": "palette-classic"},
          "custom": {
            "axisBorderShow": false,
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "hPa",
            "axisPlacement": "auto",
            "fillOpacity": 10,
            "gradientMode": "opacity",
            "hideFrom": {"legend": false, "tooltip": false, "viz": false},
            "lineWidth": 2,
            "scaleDistribution": {"type": "linear"},
            "thresholdsStyle": {"mode": "off"}
          },
          "mappings": [],
          "unit": "pressurehpa"
        },
        "overrides": []
      },
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
      "id": 3,
      "options": {
        "legend": {"calcs": ["mean", "min", "max"], "displayMode": "table", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      },
      "targets": [
        {
          "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
          "query": "from(bucket: \"weather\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"weather\")\n  |> filter(fn: (r) => r[\"_field\"] == \"press\")",
          "refId": "A"
        }
      ],
      "title": "Barometric Pressure",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
      "fieldConfig": {
        "defaults": {
          "color": {"mode": "thresholds"},
          "custom": {
            "axisBorderShow": false,
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "hPa",
            "axisPlacement": "auto",
            "fillOpacity": 15,
            "gradientMode": "none",
            "hideFrom": {"legend": false, "tooltip": false, "viz": false},
            "lineWidth": 2,
            "scaleDistribution": {"type": "linear"},
            "thresholdsStyle": {"mode": "line+area"}
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {"color": "green", "value": null},
              {"color": "red", "value": -3}
            ]
          },
          "unit": "pressurehpa"
        },
        "overrides": []
      },
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
      "id": 4,
      "options": {
        "legend": {"calcs": ["lastNotNull"], "displayMode": "table", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      },
      "targets": [
        {
          "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
          "query": "from(bucket: \"weather\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"weather\")\n  |> filter(fn: (r) => r[\"_field\"] == \"pressure_trend_3h\")",
          "refId": "A"
        }
      ],
      "title": "Pressure Trend (3h Delta)",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
      "fieldConfig": {
        "defaults": {
          "color": {"mode": "palette-classic"},
          "custom": {
            "axisBorderShow": false,
            "axisCenteredZero": false,
            "axisColorMode": "text",
            "axisLabel": "km/h",
            "axisPlacement": "auto",
            "fillOpacity": 10,
            "gradientMode": "opacity",
            "hideFrom": {"legend": false, "tooltip": false, "viz": false},
            "lineWidth": 2,
            "scaleDistribution": {"type": "linear"},
            "thresholdsStyle": {"mode": "off"}
          },
          "mappings": [],
          "unit": "velocitykmh"
        },
        "overrides": []
      },
      "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16},
      "id": 5,
      "options": {
        "legend": {"calcs": ["mean", "max"], "displayMode": "table", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      },
      "targets": [
        {
          "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
          "query": "from(bucket: \"weather\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"weather\")\n  |> filter(fn: (r) => r[\"_field\"] == \"wind\")",
          "refId": "A"
        }
      ],
      "title": "Wind Speed",
      "type": "timeseries"
    },
    {
      "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
      "fieldConfig": {
        "defaults": {
          "color": {"mode": "thresholds"},
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {"color": "green", "value": null},
              {"color": "yellow", "value": 1},
              {"color": "red", "value": 5}
            ]
          },
          "unit": "none"
        },
        "overrides": [
          {
            "matcher": {"id": "byName", "options": "lt_dist"},
            "properties": [{"id": "unit", "value": "lengthkm"}]
          }
        ]
      },
      "gridPos": {"h": 8, "w": 12, "x": 12, "y": 16},
      "id": 6,
      "options": {
        "colorMode": "value",
        "graphMode": "area",
        "justifyMode": "auto",
        "orientation": "auto",
        "percentChangeColorMode": "standard",
        "reduceOptions": {
          "calcs": ["lastNotNull"],
          "fields": "",
          "values": false
        },
        "showPercentChange": false,
        "textMode": "auto",
        "wideLayout": true
      },
      "pluginVersion": "10.0.0",
      "targets": [
        {
          "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
          "query": "from(bucket: \"weather\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"weather\")\n  |> filter(fn: (r) => r[\"_field\"] == \"lt_count\" or r[\"_field\"] == \"lt_dist\")\n  |> last()",
          "refId": "A"
        }
      ],
      "title": "Lightning: Strikes & Last Distance",
      "type": "stat"
    },
    {
      "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
      "fieldConfig": {
        "defaults": {
          "color": {"mode": "thresholds"},
          "custom": {
            "align": "auto",
            "cellOptions": {"type": "auto"},
            "inspect": false
          },
          "mappings": [],
          "thresholds": {
            "mode": "absolute",
            "steps": [
              {"color": "green", "value": null},
              {"color": "red", "value": 80}
            ]
          }
        },
        "overrides": [
          {
            "matcher": {"id": "byName", "options": "_time"},
            "properties": [{"id": "displayName", "value": "Time"}]
          },
          {
            "matcher": {"id": "byName", "options": "alert_message"},
            "properties": [{"id": "displayName", "value": "Alert"}, {"id": "custom.cellOptions", "value": {"type": "auto"}}]
          },
          {
            "matcher": {"id": "byName", "options": "_value"},
            "properties": [{"id": "displayName", "value": "Severity"}, {"id": "custom.cellOptions", "value": {"type": "color-text"}}]
          }
        ]
      },
      "gridPos": {"h": 8, "w": 24, "x": 0, "y": 24},
      "id": 7,
      "options": {
        "cellHeight": "sm",
        "footer": {"countRows": false, "fields": "", "reducer": ["sum"], "show": false},
        "showHeader": true,
        "sortBy": [{"desc": true, "displayName": "Time"}]
      },
      "pluginVersion": "10.0.0",
      "targets": [
        {
          "datasource": {"type": "influxdb", "uid": "${DS_INFLUXDB}"},
          "query": "from(bucket: \"weather\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"weather\")\n  |> filter(fn: (r) => r[\"alert_trigger\"] == \"true\")\n  |> keep(columns: [\"_time\", \"_field\", \"_value\"])\n  |> pivot(rowKey: [\"_time\"], columnKey: [\"_field\"], valueColumn: \"_value\")",
          "refId": "A"
        }
      ],
      "title": "Storm Alert Log",
      "type": "table"
    }
  ],
  "refresh": "",
  "schemaVersion": 38,
  "tags": ["weather", "storm", "iot"],
  "templating": {
    "list": [
      {
        "current": {"selected": true, "text": "InfluxDB", "value": "InfluxDB"},
        "hide": 0,
        "includeAll": false,
        "multi": false,
        "name": "DS_INFLUXDB",
        "options": [],
        "query": "influxdb",
        "refresh": 1,
        "regex": "",
        "skipUrlSync": false,
        "type": "datasource"
      }
    ]
  },
  "time": {"from": "now-24h", "to": "now"},
  "timepicker": {},
  "timezone": "",
  "title": "Weather Station",
  "uid": "weather-station",
  "version": 1,
  "weekStart": ""
}
```

- [ ] **Step 2: Verify file is valid JSON**

```bash
python3 -m json.tool backend/grafana/dashboards/weather.json > /dev/null && echo "Valid JSON"
```

---

### Task 10: Write Telegraf configuration

**Files:**
- Create: `backend/telegraf.conf`

- [ ] **Step 1: Write `telegraf.conf`**

```toml
[agent]
  interval = "10s"
  flush_interval = "10s"

[[inputs.udp_listener]]
  service_address = ":5000"
  data_format = "json"
  name_override = "weather"
  tag_keys = ["id"]

[[processors.starlark]]
  namepass = ["weather"]
  source = '''
state = {
    "history": []
}

def apply(metric):
    current_press = metric.fields.get("press")
    current_time = int(metric.time / 1000000000)

    if current_press == None:
        return metric

    state["history"].append((current_time, current_press))

    three_hours_ago = current_time - 10800
    state["history"] = [p for p in state["history"] if p[0] >= three_hours_ago]

    if len(state["history"]) < 2:
        return metric

    oldest_press = state["history"][0][1]
    pressure_trend = current_press - oldest_press
    metric.fields["pressure_trend_3h"] = pressure_trend

    if pressure_trend <= -3.0:
        metric.tags["alert_trigger"] = "true"
        metric.fields["alert_message"] = "STORM WARNING: Barometric pressure drop detected: %.1f hPa over 3 hours! Secure local perimeter." % pressure_trend

    elif metric.fields.get("lt_count", 0) > 0 and metric.fields.get("lt_dist", 99) <= 15:
        metric.tags["alert_trigger"] = "true"
        metric.fields["alert_message"] = "LIGHTNING ALERT: Direct thunder front cells counted %d km away from the base array." % int(metric.fields.get("lt_dist"))

    return metric
'''

[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8086"]
  token = "CHANGE_ME_TO_SECURE_TOKEN"
  organization = "home"
  bucket = "weather"

[[outputs.http]]
  url = "https://api.pushover.net/1/messages.json"
  method = "POST"
  data_format = "form_urlencoded"

  [outputs.http.tagpass]
    alert_trigger = ["true"]

  [outputs.http.constants]
    token = "YOUR_PUSHOVER_APP_TOKEN"
    user = "YOUR_PUSHOVER_USER_KEY"
    title = "Local Storm Alert"
    priority = "1"
    sound = "thunder"

  [outputs.http.field_mapping]
    alert_message = "message"
```

- [ ] **Step 2: Verify file was created**

```bash
cat backend/telegraf.conf
```

---

### Task 11: Final verification

- [ ] **Step 1: Verify all files exist**

```bash
find . -type f | sort
```

Expected output should include:
```
./.gitignore
./README.md
./backend/docker-compose.yml
./backend/telegraf.conf
./backend/grafana/dashboards/weather.json
./backend/grafana/datasources/influxdb.yml
./backend/grafana/grafana-dashboards-default.yaml
./firmware/weather_watcher/README.md
./firmware/weather_watcher/app.overlay
./firmware/weather_watcher/prj.conf
./firmware/weather_watcher/src/main.c
```

- [ ] **Step 2: Verify JSON is valid**

```bash
python3 -m json.tool backend/grafana/dashboards/weather.json > /dev/null && echo "Valid JSON"
```

Expected: `Valid JSON`

- [ ] **Step 3: Verify YAML files parse**

```bash
python3 -c "import yaml; yaml.safe_load(open('backend/docker-compose.yml')); print('docker-compose.yml: OK')"
python3 -c "import yaml; yaml.safe_load(open('backend/grafana/datasources/influxdb.yml')); print('influxdb.yml: OK')"
python3 -c "import yaml; yaml.safe_load(open('backend/grafana/grafana-dashboards-default.yaml')); print('grafana-dashboards-default.yaml: OK')"
```

Expected: All three print `OK`.

- [ ] **Step 4: Count firmware source lines**

```bash
wc -l firmware/weather_watcher/src/main.c
```

Expected: ~150+ lines.
