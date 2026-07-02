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
                        │  │  ~2.8µA │   │ ~2.0µA │   │ ~10µA     │   │
                        │  │ (sleep) │   │(listen)│   │(deep slp) │   │
                        │  └─────────┘   └────────┘   └───────────┘   │
                        └──────────────────────────────────────────────┘

     Active cycle: ~80mA for ~4 seconds every 15 minutes
     Sleep current: ~10µA (total system)
     Estimated runtime: 1.5 – 2 years per 18650
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
