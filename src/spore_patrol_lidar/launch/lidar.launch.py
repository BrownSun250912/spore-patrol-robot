from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = Path(get_package_share_directory("spore_patrol_lidar"))

    port = LaunchConfiguration("port")
    reversion = ParameterValue(
        LaunchConfiguration("reversion"),
        value_type=bool,
    )
    inverted = ParameterValue(
        LaunchConfiguration("inverted"),
        value_type=bool,
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "port",
                default_value="/dev/ydlidar",
                description="YDLIDAR CP210x serial device.",
            ),
            DeclareLaunchArgument(
                "reversion",
                default_value="true",
                description="Rotate the scan by 180 degrees.",
            ),
            DeclareLaunchArgument(
                "inverted",
                default_value="true",
                description="Reverse clockwise/counter-clockwise scan order.",
            ),
            Node(
                package="ydlidar_ros2_driver",
                executable="ydlidar_ros2_driver_node",
                name="ydlidar_ros2_driver_node",
                output="screen",
                emulate_tty=True,
                parameters=[
                    str(package_share / "config" / "x3_pro.yaml"),
                    {
                        "port": port,
                        "reversion": reversion,
                        "inverted": inverted,
                    },
                ],
            ),
        ]
    )
