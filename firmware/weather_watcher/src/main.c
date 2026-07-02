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
#include <stdbool.h>

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
    struct sensor_value temp = {0};
    struct sensor_value press = {0};
    struct sensor_value hum = {0};
    char json_buffer[256];
    bool bme280_ok = false;

    boot_sequence++;

    last_wind_pulse_timestamp = 0;

    gpio_pin_configure_dt(&wind_gpio, GPIO_INPUT | GPIO_PULL_UP);
    gpio_pin_interrupt_configure_dt(&wind_gpio, GPIO_INT_EDGE_TO_ACTIVE);
    gpio_init_callback(&wind_cb_data, wind_pulse_isr, BIT(wind_gpio.pin));
    gpio_add_callback(wind_gpio.port, &wind_cb_data);

    if (device_is_ready(bme280_dev) && sensor_sample_fetch(bme280_dev) == 0) {
        sensor_channel_get(bme280_dev, SENSOR_CHAN_AMBIENT_TEMP, &temp);
        sensor_channel_get(bme280_dev, SENSOR_CHAN_PRESS, &press);
        sensor_channel_get(bme280_dev, SENSOR_CHAN_HUMIDITY, &hum);
        bme280_ok = true;
    }

    if (boot_sequence == 1) {
        calibrate_as3935_antenna();
    }

    if (device_is_ready(i2c_bus)) {
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
    }

    float rps = (float)accumulated_wind_pulses / (float)SLEEP_TIME_SEC;
    float wind_kmh = (rps * 2.5) * 1.60934;

    snprintf(json_buffer, sizeof(json_buffer),
             "{\"id\":\"storm_station_01\",\"boot\":%u,\"temp\":%.2f,\"press\":%.1f,\"hum\":%.1f,\"wind\":%.2f,\"lt_count\":%u,\"lt_dist\":%u}",
             boot_sequence,
             bme280_ok ? sensor_value_to_double(&temp) : 0.0,
             bme280_ok ? sensor_value_to_double(&press) * 10.0 : 0.0,
             bme280_ok ? sensor_value_to_double(&hum) : 0.0,
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

    accumulated_wind_pulses = 0;

    esp_sleep_enable_timer_wakeup((uint64_t)SLEEP_TIME_SEC * 1000000);
    pm_state_force(0, &(struct pm_state_info){.state = PM_STATE_SOFT_OFF});
    k_sleep(K_FOREVER);

    return 0;
}
