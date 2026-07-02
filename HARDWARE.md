# Hardware Wiring Diagram

## Overview

```
                          ┌─────────────────────────────────────┐
                          │      DFRobot FireBeetle ESP32-E      │
                          │                                      │
   BME280 ────────────────┤ 3V3  GND  SCL  SDA                  │
     │                    │  │    │    │    │                    │
     ├── VCC ─────────────┤──┘    │    │    │                    │
     ├── GND ─────────────┤───────┘    │    │                    │
     ├── SCL ─────────────┤────────────┘    │                    │
     └── SDA ─────────────┤─────────────────┘                    │
                          │                                      │
   AS3935 ────────────────┤ 3V3  GND  SCL  SDA  IRQ             │
     │                    │  │    │    │    │    │               │
     ├── + (VCC) ─────────┤──┘    │    │    │    │               │
     ├── - (GND) ─────────┤───────┘    │    │    │               │
     ├── C (SCL) ─────────┤────────────┘    │    │               │
     ├── D (SDA) ─────────┤─────────────────┘    │               │
     └── IRQ ─────────────┤──────────────────────┘               │
                          │                                      │
   WS2R ──────────────────┤ GND  GPIO27                         │
     │                    │  │     │                             │
     ├── Wire 1 ──────────┤──┘     │                             │
     └── Wire 2 ──────────┤────────┘                             │
                          │                                      │
   18650 ─────────────────┤ JST PH 2.0 Battery Port              │
     │                    │  │                                   │
     ├── Red (+) ─────────┤──┘                                   │
     └── Black (-) ────────┘                                     │
                          │                                      │
                          └──────────────────┬──────────────────┘
                                             │
                                      UDP Port 5000
                                             │
                                             ▼
                          ┌─────────────────────────────────────┐
                          │   Ubuntu ARM64 Box (192.168.0.200)   │
                          └─────────────────────────────────────┘
```

---

## Pin Mapping Table

```
┌────────────────────────┬──────────────────┬──────────────────────┬─────────────┐
│ COMPONENT              │ SENSOR PAD/PIN   │ ESP32-E PIN          │ NOTES       │
├────────────────────────┼──────────────────┼──────────────────────┼─────────────┤
│                        │ VCC              │ 3V3                  │             │
│ BME280 ────────────────┤ GND              │ GND                  │ Shared I2C  │
│ (6-Pin Breakout)       │ SCL              │ GPIO 22 (SCL)        │ bus with    │
│                        │ SDA              │ GPIO 21 (SDA)        │ AS3935      │
│                        │ CSB              │ (floating)           │ Not used    │
│                        │ SDO              │ (floating)           │ Not used    │
├────────────────────────┼──────────────────┼──────────────────────┼─────────────┤
│                        │ + (VCC)          │ 3V3                  │             │
│ DFRobot AS3935 ────────┤ - (GND)          │ GND                  │ Shared I2C  │
│ (Gravity Interface)    │ C (SCL)          │ GPIO 22 (SCL)        │ bus with    │
│                        │ D (SDA)          │ GPIO 21 (SDA)        │ BME280      │
│                        │ IRQ              │ GPIO 4               │ Interrupt   │
├────────────────────────┼──────────────────┼──────────────────────┼─────────────┤
│ Inspeed WS2R ──────────┤ Wire 1           │ GND                  │ Passive     │
│ (Anemometer)           │ Wire 2           │ GPIO 27              │ reed switch │
├────────────────────────┼──────────────────┼──────────────────────┼─────────────┤
│ 18650 Battery ─────────┤ Red (+)          │ JST PH 2.0 (+)       │ Via onboard │
│ (3500mAh)              │ Black (-)        │ JST PH 2.0 (-)       │ RT9080 LDO  │
└────────────────────────┴──────────────────┴──────────────────────┴─────────────┘
```

---

## I2C Bus Detail

```
                     3V3
                      │
                      ├──────────────┬──────────────┐
                      │              │              │
                      █ Rpu          █ Rpu          █ Rpu
                      █ (internal)   █ (internal)   █ (internal)
                      │              │              │
     ESP32 GPIO 22 ───┼──────────────┼──────────────┼─── SCL
     (I2C SCL)        │              │              │
                      │         BME280          AS3935
                      │         (0x76)          (0x03)
                      │              │              │
     ESP32 GPIO 21 ───┼──────────────┼──────────────┼─── SDA
     (I2C SDA)        │              │              │
                      │              │              │
                     GND            GND            GND
```

Both sensors share the same I2C bus (SCL=GPIO22, SDA=GPIO21) using internal pull-up resistors configured in the devicetree overlay.

---

## Anemometer Wiring

```
                                      ┌─────────────┐
     GPIO 27 ─────────────────────────┤ Inspeed WS2R │
                                      │   (passive   │
     GND ─────────────────────────────┤  reed switch)│
                                      └─────────────┘

     - Order of Wire 1 / Wire 2 does not matter (passive magnetic switch).
     - Internal pull-up on GPIO 27 holds line HIGH.
     - Each rotation closes the switch, pulling GPIO 27 LOW → generates interrupt.
```

---

## Power Architecture

```
  ┌─────────────┐      ┌──────────────────────────────────────────────┐
  │ 18650 Li-Ion │      │ DFRobot FireBeetle ESP32-E                   │
  │   3.7V       │──────│ JST PH 2.0 → RT9080 LDO → 3.3V Rail         │
  │   3500mAh    │      │                                              │
  └─────────────┘      │  ┌─────────┐   ┌────────┐   ┌───────────┐   │
                        │  │ BME280  │   │ AS3935 │   │ ESP32 SoC │   │
                        │  │  ~0.1µA │   │ ~2.0µA │   │ ~10µA     │   │
                        │  │ (sleep) │   │(listen)│   │(deep slp) │   │
                        │  └─────────┘   └────────┘   └───────────┘   │
                        └──────────────────────────────────────────────┘

     Active cycle: ~75mA for ~3 seconds every 15 minutes
     Sleep current: ~14µA (total system)
     Estimated runtime: ~1.3 years per 18650 (3,500mAh)
```

---

## Power Budget & Battery Life Calculation

### Battery

```
Type:      18650 Li-Ion cylindrical
Capacity:  3,500 mAh
Nominal:   3.7V
Full:      4.2V
Cutoff:    ~3.0V (ESP32 brownout detector)
Usable:    ~3,150 mAh (90% of rated, aging/self-discharge margin)
```

### Sleep Phase (896 seconds of every 15-minute cycle)

| Component         | Mode                     | Current |
|-------------------|--------------------------|---------|
| ESP32-E RTC+RAM   | Deep sleep               | 10.0 µA |
| BME280            | Forced sleep mode        |  0.1 µA |
| AS3935            | Listen mode (EXT_RCO)    |  2.0 µA |
| RT9080 LDO        | Quiescent (no load)      |  2.0 µA |
| **Total sleep**   |                          | **14.1 µA** |

```
Sleep energy per cycle:  14.1 µA × 896 s = 12,634 µAs = 0.0035 mAh
```

### Wake Phase (~3 seconds per cycle)

| Activity            | Current  | Duration |
|---------------------|----------|----------|
| Wi-Fi handshake     | ~70 mA   | 1.5 s    |
| BME280 sample       | ~0.7 mA  | 0.3 s    |
| AS3935 register I2C | ~0.3 mA  | 0.1 s    |
| UDP send            | ~60 mA   | 0.5 s    |
| ESP32 idle (80 MHz) | ~20 mA   | 0.6 s    |
| **Average active**  | **~75 mA** for **~3 s** |           |

```
Active energy per cycle:  75,000 µA × 3 s = 225,000 µAs = 0.0625 mAh
```

### Per-Cycle & Daily Totals

```
Per cycle:  0.0035 + 0.0625 = 0.0660 mAh
Per day:    96 cycles × 0.0660 mAh = 6.34 mAh/day
Per year:   365 days × 6.34 mAh = 2,314 mAh/year
```

### Final Runtime Estimate

```
Usable capacity:                   3,150 mAh
Yearly drain (active + sleep):    2,314 mAh
Li-Ion self-discharge (~3%/yr):      95 mAh (at 25 °C)
Effective yearly drain:           2,409 mAh/year
─────────────────────────────────────────────────
Estimated runtime:  3,150 / 2,409 = 1.31 years
                    ≈ 16 months
```

### Sensitivity Table

| Variable           | Value  | Runtime     |
|--------------------|--------|-------------|
| Active time        | 2.0 s  | 1.70 years  |
| **Active time**    | **3.0 s** | **1.31 years** |
| Active time        | 4.0 s  | 0.99 years  |
|                    |        |             |
| Active current     | 50 mA  | 1.57 years  |
| **Active current** | **75 mA** | **1.31 years** |
| Active current     | 100 mA | 1.04 years  |
|                    |        |             |
| Sleep current      | 10 µA  | 1.34 years  |
| **Sleep current**  | **14 µA** | **1.31 years** |
| Sleep current      | 30 µA  | 1.17 years  |
|                    |        |             |
| Cycle interval     | 20 min | 1.52 years  |
| **Cycle interval** | **15 min** | **1.31 years** |
| Cycle interval     | 10 min | 0.99 years  |

### Voltage Profile

```
     4.2V ┤╲
          │ ╲
     3.7V ┤  ╲________ (nominal plateau, ~80% of capacity)
          │           ╲
     3.5V ┤            ╲___  (RT9080 LDO drop-out region)
          │                ╲
     3.3V ┤                 ╲
          │                  ╲__  (ESP32 minimum, ~5% capacity left)
     3.0V ┤
          └──────────────────────────────────────
          0      4      8     12     16 months

     ESP32 operates reliably down to 3.3V input at the LDO.
     Below 3.5V, the RT9080 dropout in active mode (~200mV at 80mA)
     may cause 3.3V rail sag during Wi-Fi transmit bursts.
     Deep sleep remains stable down to 3.0V.
```

---

## Assembly Checklist

- [ ] Solder BME280 header pins (6-pin) and connect 4 wires: VCC, GND, SCL, SDA
- [ ] Connect AS3935 Gravity cable: VCC, GND, SCL, SDA, IRQ to GPIO 4
- [ ] Connect WS2R anemometer: one wire to GND, other to GPIO 27
- [ ] Set AS3935 DIP switches to default I2C address (all OFF = 0x03)
- [ ] Leave BME280 CSB and SDO pins floating
- [ ] Insert charged 3500mAh 18650 into JST PH 2.0 battery holder
- [ ] Verify no shorts between 3V3 and GND with multimeter before power-on
