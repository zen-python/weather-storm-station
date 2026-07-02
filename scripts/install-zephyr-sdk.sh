#!/usr/bin/env bash
set -euo pipefail

#=============================================================================
# Zephyr SDK 1.0.1 Installer — ESP32 (ARM64 Linux)
#=============================================================================

SDK_VERSION="1.0.1"
SDK_DIR="${HOME}/zephyr-sdk-${SDK_VERSION}"

# Override with /opt if running as root or if --system passed
if [[ "$*" == *"--system"* ]]; then
    SDK_DIR="/opt/zephyr-sdk-${SDK_VERSION}"
fi
BASE_URL="https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v${SDK_VERSION}"
ARCH="linux-aarch64"

TOOLCHAINS=(
    "hosttools_${ARCH}"
    "toolchain_gnu_${ARCH}_xtensa-espressif_esp32_zephyr-elf"
)

PURPLE='\033[0;35m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${PURPLE}[ZEPHYR-SDK]${NC} $1"; }
ok()   { echo -e "${GREEN}  ✓${NC} $1"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $1"; }
fail() { echo -e "${RED}  ✗${NC} $1"; exit 1; }

#-----------------------------------------------------------------------------
# Step 0: Check architecture
#-----------------------------------------------------------------------------
log "Checking system architecture..."
HOST_ARCH=$(uname -m)
if [[ "$HOST_ARCH" != "aarch64" ]]; then
    fail "This installer is for aarch64 (ARM64). Detected: $HOST_ARCH"
fi
ok "Architecture: $HOST_ARCH"

#-----------------------------------------------------------------------------
# Step 1: Check prerequisites
#-----------------------------------------------------------------------------
log "Checking prerequisites..."
for cmd in wget tar cmake ninja python3; do
    if ! command -v "$cmd" &>/dev/null; then
        fail "Missing required command: $cmd"
    fi
done
ok "All prerequisites present (wget, tar, cmake, ninja, python3)"

#-----------------------------------------------------------------------------
# Step 2: Create SDK directory
#-----------------------------------------------------------------------------
log "Creating SDK directory: $SDK_DIR"
if [[ -d "$SDK_DIR" ]]; then
    warn "Directory already exists: $SDK_DIR"
    read -rp "Overwrite? [y/N] " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        fail "Aborted by user"
    fi
    rm -rf "$SDK_DIR"
fi
mkdir -p "$SDK_DIR"
ok "Directory ready"

#-----------------------------------------------------------------------------
# Step 3: Download toolchain bundles
#-----------------------------------------------------------------------------
WORK_DIR=$(mktemp -d /tmp/zephyr-sdk-install.XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

log "Working in: $WORK_DIR"
cd "$WORK_DIR"

for bundle in "${TOOLCHAINS[@]}"; do
    FILE="${bundle}.tar.xz"
    URL="${BASE_URL}/${FILE}"
    log "Downloading: $FILE"
    wget -q --show-progress "$URL" || fail "Failed to download: $URL"

    ok "Extracting $FILE ..."
    tar xf "$FILE" -C "$SDK_DIR" 2>/dev/null || fail "Failed to extract: $FILE"
    ok "  Installed: $bundle"
done

#-----------------------------------------------------------------------------
# Step 4: Verify installed toolchain
#-----------------------------------------------------------------------------
log "Verifying toolchain installation..."
ESP32_GCC="$SDK_DIR/xtensa-espressif_esp32_zephyr-elf/bin/xtensa-espressif_esp32_zephyr-elf-gcc"
if [[ -x "$ESP32_GCC" ]]; then
    GCC_VER=$("$ESP32_GCC" --version | head -1)
    ok "ESP32 GCC found: $GCC_VER"
else
    fail "ESP32 GCC not found at: $ESP32_GCC"
fi

#-----------------------------------------------------------------------------
# Step 5: Configure Zephyr project
#-----------------------------------------------------------------------------
log "Configuring Zephyr workspace..."

ZEPHYRPROJECT="${HOME}/zephyrproject"

# Check that zephyrproject exists
if [[ ! -d "$ZEPHYRPROJECT" ]]; then
    fail "Zephyr workspace not found at $ZEPHYRPROJECT. Run 'west init' first."
fi

# Link weather app
APPS_DIR="$ZEPHYRPROJECT/apps"
mkdir -p "$APPS_DIR"
WEATHER_APP="$(cd "$(dirname "$0")/firmware/weather_watcher" 2>/dev/null && pwd)"

if [[ -d "$WEATHER_APP" ]]; then
    ln -sf "$WEATHER_APP" "$APPS_DIR/weather_watcher" 2>/dev/null || true
    ok "Firmware symlinked: $APPS_DIR/weather_watcher → $WEATHER_APP"
else
    warn "Weather firmware not found relative to installer. Skipping symlink."
fi

#-----------------------------------------------------------------------------
# Step 6: Set environment variables
#-----------------------------------------------------------------------------
log "Setting environment variables..."

SHELL_RC=""
case "$SHELL" in
    */zsh) SHELL_RC="$HOME/.zshrc" ;;
    */bash) SHELL_RC="$HOME/.bashrc" ;;
    *) SHELL_RC="$HOME/.profile" ;;
esac

MARKER="# Zephyr SDK ${SDK_VERSION}"
if grep -q "^${MARKER}" "$SHELL_RC" 2>/dev/null; then
    warn "Zephyr SDK env vars already in $SHELL_RC — removing old block"
    sed -i "/^${MARKER}/,/^# End Zephyr SDK/d" "$SHELL_RC"
fi

cat >> "$SHELL_RC" <<EOF
${MARKER}
export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
export ZEPHYR_SDK_INSTALL_DIR=${SDK_DIR}
# End Zephyr SDK
EOF

ok "Added to $SHELL_RC"

# Source them for this session
export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
export ZEPHYR_SDK_INSTALL_DIR="$SDK_DIR"

#-----------------------------------------------------------------------------
# Step 7: Summary
#-----------------------------------------------------------------------------
cat <<EOF

=============================================================================
  Zephyr SDK ${SDK_VERSION} — Installation Complete
=============================================================================

  SDK path:     ${SDK_DIR}
  Toolchains:   xtensa-espressif_esp32_zephyr-elf
  Host tools:   cmake, dtc, openocd, qemu (all platforms)

  Env vars added to: ${SHELL_RC}
    ZEPHYR_TOOLCHAIN_VARIANT=zephyr
    ZEPHYR_SDK_INSTALL_DIR=${SDK_DIR}

  Next steps:
    source ${SHELL_RC}
    cd ${ZEPHYRPROJECT}
    west build -b esp32_devkitc/esp32/procpu -p always \\
      -d build/weather_watcher apps/weather_watcher

=============================================================================
EOF

ok "Done."
