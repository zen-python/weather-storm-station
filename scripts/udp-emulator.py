#!/usr/bin/env python3
"""
Weather Station UDP Emulator — replicas real ESP32 hardware behaviour

Every 15 minutes the ESP32 wakes from deep sleep, reads all sensor registers
in one burst, sends a single UDP JSON packet, then returns to deep sleep.

Hardware-accuracy details:
  - Wind speed:   pulses accumulated by WS2R reed switch during the entire
                  15-minute sleep block, read once on wake → average km/h
  - Lightning:    AS3935 continuously listens during sleep. Strikes captured
                  in hardware registers, read once on wake → count + distance
  - BME280:       forced-mode sample on wake → temp, pressure, humidity
  - State:        RTC memory persists across sleep → boot counter increments

Open-Meteo provides current surface readings. We accumulate lightning
probabilistically each cycle and report all strikes at wake.

Usage:
  python3 udp-emulator.py --city "Des Moines" --interval 900
  python3 udp-emulator.py --lat 51.5074 --lon -0.1278 --interval 900
"""

import argparse
import json
import math
import os
import random
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TELEGRAF_HOST = os.environ.get("TELEGRAF_HOST", "127.0.0.1")
TELEGRAF_PORT = int(os.environ.get("TELEGRAF_PORT", "5000"))
STATION_ID = os.environ.get("STATION_ID", "storm_station_01")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


# ---------------------------------------------------------------------------
#  Simulated hardware registers (mimic ESP32 RTC_DATA_ATTR retention)
# ---------------------------------------------------------------------------
class SimulatedHardware:
    """State retained across deep sleep cycles, like ESP32 RTC memory."""

    def __init__(self):
        self.boot_sequence = 0
        self.accumulated_wind_ticks = 0
        self.total_lightning_strikes = 0
        self.last_lightning_distance = 0

        self._wind_start = 0.0          # ticks accumulated so far (tracked across sleep)
        self._lightning_log = []        # (count, distance) per interval


# ---------------------------------------------------------------------------
#  Geocoding
# ---------------------------------------------------------------------------
def geocode(city):
    params = urllib.parse.urlencode({"name": city, "count": 1, "language": "en"})
    url = f"{GEOCODING_URL}?{params}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    if not data.get("results"):
        raise SystemExit(f"City not found: {city}")
    r = data["results"][0]
    return r["latitude"], r["longitude"], f"{r['name']}, {r.get('country', '')}"


# ---------------------------------------------------------------------------
#  Weather fetch (Open-Meteo, no API key)
# ---------------------------------------------------------------------------
def fetch_weather(lat, lon):
    params = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "relative_humidity_2m",
            "surface_pressure",
            "wind_speed_10m",
        ],
        "wind_speed_unit": "ms",
    }, doseq=True)
    url = f"{OPEN_METEO_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        cur = data.get("current", {})
        return {
            "temp": cur.get("temperature_2m"),
            "hum": cur.get("relative_humidity_2m"),
            "press": cur.get("surface_pressure"),
            "wind_ms": cur.get("wind_speed_10m"),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
#  Lightning simulation (mimics AS3935 hardware register accumulation)
# ---------------------------------------------------------------------------
def simulate_lightning_interval(interval_seconds):
    """
    Simulate the AS3935 listening continuously during the deep-sleep block.
    Returns (total_strikes_this_cycle, closest_distance_km).

    Lightning probability scales with the interval length.
    The AS3935 captures all strikes and the ESP32 reads them on wake.
    """
    strikes = []
    check_count = max(1, interval_seconds // 60)      # check once per minute of sleep

    for _ in range(check_count):
        r = random.random()

        if r < 0.002:                              # ~0.2%/min of close strike
            strikes.append(random.uniform(1, 15))
        elif r < 0.008:                            # ~0.6%/min of moderate
            strikes.append(random.uniform(15, 40))
        elif r < 0.025:                            # ~1.7%/min of distant
            strikes.append(random.uniform(40, 100))

    if strikes:
        return len(strikes), min(strikes)
    return 0, 0


# ---------------------------------------------------------------------------
#  Wind simulation (mimics WS2R reed-switch pulse accumulation)
# ---------------------------------------------------------------------------
def simulate_wind_ticks(wind_ms, interval_seconds):
    """
    Simulate the WS2R anemometer accumulating reed-switch closures
    during the deep-sleep block. On wake, the ESP32 reads total ticks.

    WS2R spec: 2.5 mph per Hz (one closure per revolution).
    We convert m/s → mph → revs/sec → total revs over interval.
    Each revolution produces one pulse.

    Returns total tick count for the interval.
    """
    if wind_ms is None or wind_ms < 0:
        return 0

    mph = wind_ms * 2.23694                  # m/s → mph
    rps = mph / 2.5                          # revolutions per second (mph / mph-per-rps)
    ticks = int(rps * interval_seconds)
    return max(0, ticks)


# ---------------------------------------------------------------------------
#  Build JSON payload (matches ESP32 firmware format exactly)
# ---------------------------------------------------------------------------
def build_payload(sim, weather, interval_seconds):
    if weather is None:
        weather = {"temp": None, "hum": None, "press": None, "wind_ms": None}

    # Wind:  accumulated ticks ÷ seconds = rps → mph → km/h
    ticks = simulate_wind_ticks(weather["wind_ms"], interval_seconds)
    sim.accumulated_wind_ticks += ticks
    rps = sim.accumulated_wind_ticks / interval_seconds if interval_seconds > 0 else 0
    wind_kmh = (rps * 2.5) * 1.60934       # same Inspeed formula as firmware
    sim.accumulated_wind_ticks = 0          # reset for next cycle

    # Lightning: AS3935 registers read on wake
    strikes_this_cycle, closest_dist = simulate_lightning_interval(interval_seconds)
    if strikes_this_cycle > 0:
        sim.total_lightning_strikes += strikes_this_cycle
        sim.last_lightning_distance = closest_dist

    return json.dumps({
        "id": STATION_ID,
        "boot": sim.boot_sequence,
        "temp": round(weather["temp"] or 0, 2),
        "press": round(weather["press"] or 1013.25, 1),
        "hum": round(weather["hum"] or 50, 1),
        "wind": round(wind_kmh, 2),
        "lt_count": sim.total_lightning_strikes,
        "lt_dist": sim.last_lightning_distance,
    })


# ---------------------------------------------------------------------------
#  UDP send
# ---------------------------------------------------------------------------
def send_udp(payload, host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(payload.encode(), (host, port))
    sock.close()


# ---------------------------------------------------------------------------
#  Main wake cycle
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Weather Station UDP Emulator")
    loc = parser.add_mutually_exclusive_group()
    loc.add_argument("--city", help="City name")
    loc.add_argument("--lat", type=float, default=40.4168, help="Latitude")
    parser.add_argument("--lon", type=float, default=-3.7038, help="Longitude")
    parser.add_argument("--interval", type=int, default=0,
                        help="Seconds between wake cycles (0=one shot)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print JSON, don't send UDP")
    parser.add_argument("--host", default=TELEGRAF_HOST)
    parser.add_argument("--port", type=int, default=TELEGRAF_PORT)
    args = parser.parse_args()

    if args.city:
        lat, lon, name = geocode(args.city)
    else:
        lat, lon, name = args.lat, args.lon, f"{args.lat},{args.lon}"

    interval = args.interval if args.interval > 0 else 900
    sim = SimulatedHardware()

    print(f"Station: {STATION_ID}  |  Location: {name} ({lat}, {lon})")
    print(f"Sleep interval: {interval}s ({interval//60} min)")
    print(f"Target: {args.host}:{args.port}/udp")
    print(f"{'Dry-run, not sending' if args.dry_run else 'Sending live'}")
    print()

    while True:
        # ---- DEEP SLEEP (simulated) ----
        # During this time the AS3935 is listening, anemometer is turning,
        # BME280 is in sleep mode. The ESP32 CPU is off at ~10 uA.
        sleep_start = time.time()

        # ---- WAKE ----
        # ESP32 wakes, RTC variables survive, boot counter increments
        sim.boot_sequence += 1

        # Fetch current conditions (BME280 forced-mode sample equivalent)
        weather = fetch_weather(lat, lon)

        # Build and send payload
        payload = build_payload(sim, weather, interval)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")

        if args.dry_run:
            print(f"[{ts}] boot={sim.boot_sequence} {payload}")
        else:
            send_udp(payload, args.host, args.port)
            flags = []
            d = json.loads(payload)
            if d["lt_count"] > 0:
                flags.append(f"LT:{d['lt_count']}strikes({d['lt_dist']}km)")
            flag = f"  ({', '.join(flags)})" if flags else ""
            print(f"[{ts}] boot={sim.boot_sequence}{flag} "
                  f"T={d['temp']}C  H={d['hum']}%  P={d['press']}hPa  W={d['wind']}km/h")
            sys.stdout.flush()

        if args.interval <= 0:
            break

        # Stay awake for the actual elapsed time then sleep again
        elapsed = time.time() - sleep_start
        remaining = max(0, interval - elapsed)
        time.sleep(remaining)


if __name__ == "__main__":
    main()
