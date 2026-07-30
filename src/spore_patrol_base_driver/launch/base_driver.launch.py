from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = Path(
        get_package_share_directory("spore_patrol_base_driver")
    )
    port = LaunchConfiguration("port")
    publish_tf = LaunchConfiguration("publish_tf")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "port",
                default_value="/dev/ttyACM0",
                description="STM32 ROS serial device.",
            ),
            DeclareLaunchArgument(
                "publish_tf",
                default_value="true",
                description="Publish odom to base_footprint from the driver.",
            ),
            Node(
                package="spore_patrol_base_driver",
                executable="base_driver_node",
                name="spore_patrol_base_driver",
                output="screen",
                parameters=[
                    str(package_share / "config" / "base_driver.yaml"),
                    {
                        "port": port,
                        "publish_tf": ParameterValue(
                            publish_tf,
                            value_type=bool,
                        ),
                    },
                ],
            ),
        ]
    )
