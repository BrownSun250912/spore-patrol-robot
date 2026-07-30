from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    localization_share = Path(
        get_package_share_directory("spore_patrol_localization")
    )
    slam_share = Path(get_package_share_directory("spore_patrol_slam"))

    base_port = LaunchConfiguration("base_port")
    lidar_port = LaunchConfiguration("lidar_port")
    rviz = LaunchConfiguration("rviz")

    return LaunchDescription(
        [
            DeclareLaunchArgument("base_port", default_value="/dev/ttyACM0"),
            DeclareLaunchArgument("lidar_port", default_value="/dev/ydlidar"),
            DeclareLaunchArgument("rviz", default_value="true"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(slam_share / "launch" / "mapping.launch.py")
                ),
                launch_arguments={
                    "base_port": base_port,
                    "lidar_port": lidar_port,
                    "rviz": rviz,
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
