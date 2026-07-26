from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import xacro


def generate_launch_description():
    description_share = Path(
        get_package_share_directory("spore_patrol_description")
    )
    driver_share = Path(
        get_package_share_directory("spore_patrol_base_driver")
    )
    robot_description = xacro.process_file(
        str(description_share / "urdf" / "spore_patrol_robot.urdf.xacro")
    ).toxml()

    port = LaunchConfiguration("port")
    use_rviz = LaunchConfiguration("rviz")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "port",
                default_value="/dev/ttyACM0",
                description="STM32 ROS serial device.",
            ),
            DeclareLaunchArgument(
                "rviz",
                default_value="true",
                description="Start RViz with the real chassis.",
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[{"robot_description": robot_description}],
                output="screen",
            ),
            Node(
                package="spore_patrol_base_driver",
                executable="base_driver_node",
                name="spore_patrol_base_driver",
                output="screen",
                parameters=[
                    str(driver_share / "config" / "base_driver.yaml"),
                    {"port": port},
                ],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=[
                    "-d",
                    str(description_share / "rviz" / "model.rviz"),
                ],
                condition=IfCondition(use_rviz),
                output="screen",
            ),
        ]
    )
