#!/usr/bin/env bash

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workspace_dir="$(cd -- "${script_dir}/.." && pwd)"
sdk_install_dir="${workspace_dir}/.vendor/ydlidar_sdk_install"

if [[ ! -f "${sdk_install_dir}/lib/cmake/ydlidar_sdk/ydlidar_sdkConfig.cmake" ]]; then
  echo "YDLIDAR SDK is not installed under ${sdk_install_dir}." >&2
  echo "Run tools/setup_ydlidar_dependencies.sh first." >&2
  return 1 2>/dev/null || exit 1
fi

export CMAKE_PREFIX_PATH="${sdk_install_dir}${CMAKE_PREFIX_PATH:+:${CMAKE_PREFIX_PATH}}"
export LIBRARY_PATH="${sdk_install_dir}/lib${LIBRARY_PATH:+:${LIBRARY_PATH}}"
export PKG_CONFIG_PATH="${sdk_install_dir}/lib/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
