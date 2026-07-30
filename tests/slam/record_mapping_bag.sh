#!/usr/bin/env bash
set -euo pipefail

script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
workspace_root="$(CDPATH= cd -- "${script_directory}/../.." && pwd)"

if ! command -v ros2 >/dev/null 2>&1; then
  echo "ros2 was not found. Source /opt/ros/humble/setup.bash and install/setup.bash first." >&2
  exit 2
fi

timestamp="$(date +%Y%m%d_%H%M%S)"
result_directory="${workspace_root}/tests/results/${timestamp}_mapping"
bag_directory="${result_directory}/rosbag"
mkdir -p "${result_directory}"

{
  date --iso-8601=seconds
  printf 'workspace=%s\n' "${workspace_root}"
  printf 'command=ros2 bag record\n'
} > "${result_directory}/metadata.txt"

printf 'Recording mapping data in:\n%s\n' "${bag_directory}"
printf 'Drive slowly. Press Ctrl+C once after returning to the start.\n'

exec ros2 bag record \
  --output "${bag_directory}" \
  /scan \
  /odom \
  /odometry/filtered \
  /tf \
  /tf_static \
  /imu/data_raw \
  /imu/data_calibrated \
  /battery_state \
  /diagnostics \
  /cmd_vel \
  /map \
  /map_metadata \
  /rosout
