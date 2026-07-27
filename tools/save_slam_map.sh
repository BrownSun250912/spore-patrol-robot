#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "Usage: tools/save_slam_map.sh MAP_NAME" >&2
  echo "MAP_NAME may contain letters, numbers, underscores and hyphens." >&2
  exit 2
fi

script_directory="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
workspace_root="$(CDPATH= cd -- "${script_directory}/.." && pwd)"
map_directory="${workspace_root}/maps"
map_base="${map_directory}/$1"

mkdir -p "${map_directory}"
for suffix in yaml pgm posegraph data; do
  if [[ -e "${map_base}.${suffix}" ]]; then
    echo "Refusing to overwrite ${map_base}.${suffix}" >&2
    exit 1
  fi
done

printf 'Saving occupancy map to %s.yaml and %s.pgm\n' \
  "${map_base}" "${map_base}"
ros2 run nav2_map_server map_saver_cli \
  -f "${map_base}" \
  --ros-args \
  -p save_map_timeout:=10.0

if ros2 service type /slam_toolbox/serialize_map >/dev/null 2>&1; then
  printf 'Saving SLAM pose graph to %s.posegraph and %s.data\n' \
    "${map_base}" "${map_base}"
  ros2 service call \
    /slam_toolbox/serialize_map \
    slam_toolbox/srv/SerializePoseGraph \
    "{filename: \"${map_base}\"}"
else
  echo "Map image saved, but /slam_toolbox/serialize_map is unavailable." >&2
fi
