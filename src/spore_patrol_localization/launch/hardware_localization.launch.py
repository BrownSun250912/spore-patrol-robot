from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    bringup_share = Path(
        get_package_share_directory("spore_patrol_bringup")
    )
    localization_share = Path(
        get_package_share_directory("spore_patrol_localization")
    )

    port = LaunchConfiguration("port")
    lidar = LaunchConfiguration("lidar")
    lidar_port = LaunchConfiguration("lidar_port")
    rviz = LaunchConfiguration("rviz")

    return LaunchDescription(
        [
            DeclareLaunchArgument("port", default_value="/dev/ttyACM0"),
            DeclareLaunchArgument("lidar", default_value="false"),
            DeclareLaunchArgument("lidar_port", default_value="/dev/ydlidar"),
            DeclareLaunchArgument("rviz", default_value="true"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(bringup_share / "launch" / "hardware.launch.py")
                ),
                launch_arguments={
                    "port": port,
                    "lidar": lidar,
                    "lidar_port": lidar_port,
                    "rviz": rviz,
                    # Exactly one node may own odom -> base_footprint.
                    "base_publish_tf": "false",
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(localization_share / "launch" / "local_ekf.launch.py")
                )
            ),
        ]
    )
