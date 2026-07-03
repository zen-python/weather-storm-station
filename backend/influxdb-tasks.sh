#!/usr/bin/env bash
set -euo pipefail
#=============================================================================
# InfluxDB Tasks Setup — Long-window historical trend analysis
#
# Run this ONCE after docker compose up -d on the ARM64 server:
#   bash influxdb-tasks.sh
#
# Requires: INFLUX_TOKEN, INFLUX_ORG, INFLUX_URL
#=============================================================================

INFLUX_URL="${INFLUX_URL:-http://localhost:8086}"
INFLUX_ORG="${INFLUX_ORG:-home}"
INFLUX_TOKEN="${INFLUX_TOKEN:-CHANGE_ME_TO_SECURE_TOKEN}"
BUCKET="weather"

echo "=== Setting up InfluxDB tasks ==="
echo "URL:  $INFLUX_URL"
echo "Org:  $INFLUX_ORG"
echo ""

#-----------------------------------------------------------------------------
# Task 1: 24-hour pressure trend (runs every 15 min)
#-----------------------------------------------------------------------------
PAYLOAD_24H=$(cat <<FLUX
option task = {
    name: "pressure_trend_24h",
    every: 15m,
    offset: 0s,
}

from(bucket: "${BUCKET}")
    |> range(start: -24h)
    |> filter(fn: (r) => r._measurement == "weather")
    |> filter(fn: (r) => r._field == "press")
    |> sort(columns: ["_time"])
    |> difference(nonNegative: false)
    |> cumulativeSum()
    |> last()
    |> map(fn: (r) => ({r with _field: "pressure_trend_24h"}))
    |> to(bucket: "${BUCKET}")
FLUX
)

#-----------------------------------------------------------------------------
# Task 2: 7-day pressure trend (runs every hour)
#-----------------------------------------------------------------------------
PAYLOAD_7D=$(cat <<FLUX
option task = {
    name: "pressure_trend_7d",
    every: 1h,
    offset: 0s,
}

from(bucket: "${BUCKET}")
    |> range(start: -7d)
    |> filter(fn: (r) => r._measurement == "weather")
    |> filter(fn: (r) => r._field == "press")
    |> sort(columns: ["_time"])
    |> difference(nonNegative: false)
    |> cumulativeSum()
    |> last()
    |> map(fn: (r) => ({r with _field: "pressure_trend_7d"}))
    |> to(bucket: "${BUCKET}")
FLUX
)

#-----------------------------------------------------------------------------
# Task 3: Daily summary stats (runs every hour, writes aggregates)
#-----------------------------------------------------------------------------
PAYLOAD_SUMMARY=$(cat <<FLUX
option task = {
    name: "weather_daily_summary",
    every: 1h,
    offset: 0s,
}

from(bucket: "${BUCKET}")
    |> range(start: -24h)
    |> filter(fn: (r) => r._measurement == "weather")
    |> filter(fn: (r) => r._field == "temp" or r._field == "hum" or r._field == "press" or r._field == "wind")
    |> aggregateWindow(every: 24h, fn: mean, createEmpty: false)
    |> set(key: "_measurement", value: "weather_daily")
    |> to(bucket: "${BUCKET}")
FLUX
)

echo "Creating task: pressure_trend_24h ..."
curl -sS -X POST "${INFLUX_URL}/api/v2/tasks" \
    -H "Authorization: Token ${INFLUX_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"org\": \"${INFLUX_ORG}\", \"flux\": $(echo "$PAYLOAD_24H" | jq -Rs .), \"status\": \"active\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  OK: {d[\"name\"]} (id={d[\"id\"][:8]}...)')"

echo "Creating task: pressure_trend_7d ..."
curl -sS -X POST "${INFLUX_URL}/api/v2/tasks" \
    -H "Authorization: Token ${INFLUX_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"org\": \"${INFLUX_ORG}\", \"flux\": $(echo "$PAYLOAD_7D" | jq -Rs .), \"status\": \"active\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  OK: {d[\"name\"]} (id={d[\"id\"][:8]}...)')"

echo "Creating task: weather_daily_summary ..."
curl -sS -X POST "${INFLUX_URL}/api/v2/tasks" \
    -H "Authorization: Token ${INFLUX_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"org\": \"${INFLUX_ORG}\", \"flux\": $(echo "$PAYLOAD_SUMMARY" | jq -Rs .), \"status\": \"active\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  OK: {d[\"name\"]} (id={d[\"id\"][:8]}...)')"

echo ""
echo "=== Done. Verify: ==="
echo "  curl -H 'Authorization: Token ${INFLUX_TOKEN}' ${INFLUX_URL}/api/v2/tasks?org=${INFLUX_ORG}"
