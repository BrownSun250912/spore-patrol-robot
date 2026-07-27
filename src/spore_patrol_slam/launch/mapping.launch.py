from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    package_share = Path(
        get_package_share_directory("spore_patrol_slam")
    )
    bringup_share = Path(
        get_package_share_directory("spore_patrol_bringup")
    )
    slam_toolbox_share = Path(
        get_package_share_directory("slam_toolbox")
    )

    base_port = LaunchConfiguration("base_port")
    lidar_port = LaunchConfiguration("lidar_port")
    slam_params_file = LaunchConfiguration("slam_params_file")
    use_rviz = LaunchConfiguration("rviz")
    use_sim_time = LaunchConfiguration("use_sim_time")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "base_port",
                default_value="/dev/ttyACM0",
                description="STM32 chassis serial device.",
            ),
            DeclareLaunchArgument(
                "lidar_port",
                default_value="/dev/ydlidar",
                description="YDLIDAR X3 Pro serial device.",
            ),
            DeclareLaunchArgument(
                "slam_params_file",
                default_value=str(package_share / "config" / "mapping.yaml"),
                description="SLAM Toolbox parameter file.",
            ),
            DeclareLaunchArgument(
                "rviz",
                default_value="true",
                description="Start the mapping RViz configuration.",
            ),
            DeclareLaunchArgument(
                "use_sim_time",
                default_value="false",
                description="Use simulation clock instead of the host clock.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(bringup_share / "launch" / "hardware.launch.py")
                ),
                launch_arguments={
                    "port": base_port,
                    "lidar": "true",
                    "lidar_port": lidar_port,
                    "rviz": "false",
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(
                        slam_toolbox_share
                        / "launch"
                        / "online_async_launch.py"
                    )
                ),
                launch_arguments={
                    "autostart": "true",
                    "slam_params_file": slam_params_file,
                    "use_lifecycle_manager": "false",
                    "use_sim_time": use_sim_time,
                }.items(),
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=[
                    "-d",
                    str(package_share / "rviz" / "mapping.rviz"),
                ],
                condition=IfCondition(use_rviz),
                output="screen",
            ),
        ]
    )
