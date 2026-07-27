from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import xacro


def generate_launch_description():
    lidar_share = Path(get_package_share_directory("spore_patrol_lidar"))
    description_share = Path(
        get_package_share_directory("spore_patrol_description")
    )
    robot_description = xacro.process_file(
        str(description_share / "urdf" / "spore_patrol_robot.urdf.xacro")
    ).toxml()

    port = LaunchConfiguration("port")
    reversion = LaunchConfiguration("reversion")
    inverted = LaunchConfiguration("inverted")

    return LaunchDescription(
        [
            DeclareLaunchArgument("port", default_value="/dev/ydlidar"),
            DeclareLaunchArgument("reversion", default_value="true"),
            DeclareLaunchArgument("inverted", default_value="true"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(lidar_share / "launch" / "lidar.launch.py")
                ),
                launch_arguments={
                    "port": port,
                    "reversion": reversion,
                    "inverted": inverted,
                }.items(),
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[{"robot_description": robot_description}],
                output="screen",
            ),
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                arguments=[
                    "--x",
                    "0",
                    "--y",
                    "0",
                    "--z",
                    "0",
                    "--yaw",
                    "0",
                    "--pitch",
                    "0",
                    "--roll",
                    "0",
                    "--frame-id",
                    "world",
                    "--child-frame-id",
                    "base_footprint",
                ],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=[
                    "-d",
                    str(lidar_share / "rviz" / "x3_pro.rviz"),
                ],
                output="screen",
            ),
        ]
    )
