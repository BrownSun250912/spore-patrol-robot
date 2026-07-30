cmake_minimum_required(VERSION 3.8)
project(spore_patrol_localization)

find_package(ament_cmake REQUIRED)

install(
  PROGRAMS scripts/imu_bias_calibrator.py
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

install(
  FILES README.md
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
