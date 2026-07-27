#!/usr/bin/env bash
set -euo pipefail

device="${1:-/dev/ttyUSB0}"
rule_path="/etc/udev/rules.d/99-spore-patrol-ydlidar.rules"

if [[ ! -c "${device}" ]]; then
  echo "Serial device ${device} does not exist." >&2
  exit 1
fi

serial_short="$(
  udevadm info --query=property --name="${device}" |
    sed -n 's/^ID_SERIAL_SHORT=//p' |
    head -n 1
)"

if [[ -z "${serial_short}" ]]; then
  echo "The adapter has no ID_SERIAL_SHORT; no broad CP210x rule was installed." >&2
  echo "Use /dev/serial/by-path or keep the adapter on a dedicated USB port." >&2
  exit 1
fi

temporary_rule="$(mktemp)"
trap 'rm -f "${temporary_rule}"' EXIT

printf '%s\n' \
  'SUBSYSTEM=="tty", KERNEL=="ttyUSB*", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", ATTRS{serial}=="'"${serial_short}"'", SYMLINK+="ydlidar", GROUP="dialout", MODE="0660"' \
  > "${temporary_rule}"

sudo install -m 0644 "${temporary_rule}" "${rule_path}"
sudo udevadm control --reload-rules
sudo udevadm trigger

echo "Installed ${rule_path} for serial ${serial_short}."
echo "Reconnect the adapter, then check: ls -l /dev/ydlidar"
