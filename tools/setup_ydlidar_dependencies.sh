#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workspace_dir="$(cd -- "${script_dir}/.." && pwd)"
vendor_dir="${workspace_dir}/.vendor"
sdk_dir="${vendor_dir}/YDLidar-SDK"
sdk_build_dir="${vendor_dir}/ydlidar_sdk_build"
sdk_install_dir="${vendor_dir}/ydlidar_sdk_install"
driver_dir="${workspace_dir}/src/ydlidar_ros2_driver"

sdk_url="https://github.com/YDLIDAR/YDLidar-SDK.git"
sdk_revision="01cdda4f2b36dff2a706d0535c64228d863c7411"
driver_url="https://github.com/YDLIDAR/ydlidar_ros2_driver.git"
driver_revision="4ef70d3f32a85704ade0be54b214f3763b1ab3e8"

checkout_dependency() {
  local url="$1"
  local revision="$2"
  local destination="$3"

  if [[ ! -d "${destination}/.git" ]]; then
    git clone "${url}" "${destination}"
  fi

  # FAT/exFAT-style removable filesystems do not preserve executable bits.
  # Ignoring file-mode-only changes keeps the dependency checkout clean.
  git -C "${destination}" config core.filemode false

  if ! git -C "${destination}" diff --quiet ||
     ! git -C "${destination}" diff --cached --quiet; then
    echo "Refusing to overwrite local changes in ${destination}" >&2
    return 1
  fi

  git -C "${destination}" fetch origin "${revision}"
  git -C "${destination}" checkout --detach "${revision}"
}

mkdir -p "${vendor_dir}" "${workspace_dir}/src"
checkout_dependency "${sdk_url}" "${sdk_revision}" "${sdk_dir}"
checkout_dependency "${driver_url}" "${driver_revision}" "${driver_dir}"

cmake \
  -S "${sdk_dir}" \
  -B "${sdk_build_dir}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="${sdk_install_dir}" \
  -DBUILD_SHARED_LIBS=OFF \
  -DBUILD_EXAMPLES=OFF \
  -DBUILD_TEST=OFF \
  -DCMAKE_DISABLE_FIND_PACKAGE_SWIG=TRUE \
  -DCMAKE_DISABLE_FIND_PACKAGE_PythonInterp=TRUE \
  -DCMAKE_DISABLE_FIND_PACKAGE_PythonLibs=TRUE

cmake --build "${sdk_build_dir}" --parallel
cmake --install "${sdk_build_dir}"

echo
echo "YDLIDAR dependencies are ready."
echo "Before colcon build, run:"
echo "  source \"${workspace_dir}/tools/ydlidar_env.sh\""
