#!/usr/bin/env python3
"""
Weather Station UDP Emulator — sends realistic weather data to Telegraf.

Uses the free Open-Meteo API (no key required) for real current conditions,
then broadcasts JSON packets to the Telegraf socket_listener on UDP :5000.

Usage:
  # Single shot with default coordinates (Madrid)
  python3 udp-emulator.py

  # Custom location with periodic send every 15 minutes
  python3 udp-emulator.py --lat 40.4168 --lon -3.7038 --interval 900

  # City name (auto geocoded)
  python3 udp-emulator.py --city "Barcelona" --interval 900

  # Dry run (print JSON, don't send)
  python3 udp-emulator.py --dry-run
"""

import argparse
import json
import random
import socket
import sys
import time
import urllib.request
import urllib.parse
import os

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
TELEGRAF_HOST = os.environ.get("TELEGRAF_HOST", "127.0.0.1")
TELEGRAF_PORT = int(os.environ.get("TELEGRAF_PORT", "5000"))
STATION_ID = os.environ.get("STATION_ID", "storm_station_01")


def geocode(city):
    params = urllib.parse.urlencode({"name": city, "count": 1, "language": "en"})
    url = f"{GEOCODING_URL}?{params}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())
    if not data.get("results"):
        raise SystemExit(f"City not found: {city}")
    r = data["results"][0]
    return r["latitude"], r["longitude"], f"{r['name']}, {r.get('country', '')}"


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
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())

    current = data.get("current", {})
    return {
        "temp": current.get("temperature_2m"),
        "hum": current.get("relative_humidity_2m"),
        "press": current.get("surface_pressure"),       # hPa at surface
        "wind_ms": current.get("wind_speed_10m"),        # m/s, convert to km/h
    }


def simulate_lightning():
    """Randomly generate lightning data (Open-Meteo lacks this)."""
    r = random.random()
    if r < 0.05:                                  # 5% chance of lightning strike
        dist = round(random.uniform(1, 40), 1)
        count = random.randint(1, 5)
    elif r < 0.15:                                 # 10% chance of distant
        dist = round(random.uniform(40, 100), 1)
        count = random.randint(1, 3)
    else:
        dist = 0
        count = 0
    return count, dist


def build_payload(weather, boot_seq, lt_count, lt_dist):
    wind_kmh = (weather["wind_ms"] or 0) * 3.6
    return json.dumps({
        "id": STATION_ID,
        "boot": boot_seq,
        "temp": round(weather["temp"] or 0, 2),
        "press": round(weather["press"] or 1013.25, 1),
        "hum": round(weather["hum"] or 50, 1),
        "wind": round(wind_kmh, 2),
        "lt_count": lt_count,
        "lt_dist": lt_dist,
    })


def send(payload):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(payload.encode(), (TELEGRAF_HOST, TELEGRAF_PORT))
    sock.close()


def resolve_location(args):
    if args.city:
        lat, lon, name = geocode(args.city)
        print(f"Location: {name} ({lat}, {lon})")
        return lat, lon
    else:
        print(f"Location: {args.lat}, {args.lon}")
        return args.lat, args.lon


def main():
    parser = argparse.ArgumentParser(description="Weather Station UDP Emulator")
    loc = parser.add_mutually_exclusive_group()
    loc.add_argument("--city", help="City name (auto geocoded)")
    loc.add_argument("--lat", type=float, default=40.4168, help="Latitude")
    parser.add_argument("--lon", type=float, default=-3.7038, help="Longitude")
    parser.add_argument("--interval", type=int, default=0,
                        help="Seconds between sends (0=single shot)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print JSON, don't send UDP")
    parser.add_argument("--host", default=TELEGRAF_HOST, help="Telegraf host")
    parser.add_argument("--port", type=int, default=TELEGRAF_PORT, help="Telegraf UDP port")
    args = parser.parse_args()

    lat, lon = resolve_location(args)
    boot_seq = 0

    while True:
        boot_seq += 1

        try:
            weather = fetch_weather(lat, lon)
        except Exception as e:
            print(f"API error: {e}", file=sys.stderr)
            weather = {"temp": None, "hum": None, "press": None, "wind_ms": None}

        lt_count, lt_dist = simulate_lightning()
        payload = build_payload(weather, boot_seq, lt_count, lt_dist)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        if args.dry_run:
            print(f"[{timestamp}] {payload}")
        else:
            send(payload)
            flags = []
            if lt_count > 0:
                flags.append(f"lightning:{lt_count}@{lt_dist}km")
            flag_str = f" ({', '.join(flags)})" if flags else ""
            print(f"[{timestamp}] sent{flag_str}: {payload}")

        if args.interval <= 0:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
