#!/usr/bin/env bash
set -euo pipefail

#=============================================================================
# Docker Build Script — Weather Watcher Zephyr Firmware
#=============================================================================

IMAGE="ghcr.io/zephyrproject-rtos/zephyr-build:main"
BOARD="esp32_devkitc/esp32/procpu"
APP_DIR="$(cd "$(dirname "$0")/../firmware/weather_watcher" && pwd)"
BUILD_DIR="${APP_DIR}/build"

echo "=== Weather Watcher Docker Build ==="
echo "Board:  ${BOARD}"
echo "App:    ${APP_DIR}"
echo "Image:  ${IMAGE}"
echo ""

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker not found. Install Docker first."
    exit 1
fi

# Check Wi-Fi credentials
if grep -q 'YOUR_HOME_WIFI_NAME' "${APP_DIR}/src/main.c"; then
    echo "WARNING: Wi-Fi credentials not set."
    echo "  Edit src/main.c and set WIFI_SSID and WIFI_PASS before building."
    echo ""
fi

# Pull latest image
echo "Pulling Docker image (this may take a while on first run)..."
docker pull "${IMAGE}" 2>&1 | tail -1

# Clean previous build
rm -rf "${BUILD_DIR}"

# Build
echo ""
echo "Building..."
docker run --rm \
    -v "${APP_DIR}:/app" \
    --workdir /app \
    "${IMAGE}" \
    west build -b "${BOARD}" -p always -d build /app

echo ""
echo "Build complete."
echo "Binary: ${BUILD_DIR}/zephyr/zephyr.bin"
echo ""
echo "To flash:"
echo "  west flash -d ${BUILD_DIR}"
echo "  # or: esptool.py --chip esp32 write_flash 0x0 ${BUILD_DIR}/zephyr/zephyr.bin"
