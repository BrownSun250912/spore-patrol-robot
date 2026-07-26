from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import xacro


def generate_launch_description():
    description_share = Path(
        get_package_share_directory("spore_patrol_description")
    )
    sim_share = Path(get_package_share_directory("spore_patrol_sim"))
    gazebo_share = Path(get_package_share_directory("gazebo_ros"))

    robot_description = xacro.process_file(
        str(description_share / "urdf" / "spore_patrol_robot.urdf.xacro")
    ).toxml()
    use_rviz = LaunchConfiguration("rviz")
    use_gui = LaunchConfiguration("gui")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "rviz",
                default_value="true",
                description="Start RViz alongside Gazebo.",
            ),
            DeclareLaunchArgument(
                "gui",
                default_value="true",
                description="Start the Gazebo graphical client.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(gazebo_share / "launch" / "gazebo.launch.py")
                ),
                launch_arguments={
                    "world": str(sim_share / "worlds" / "farmland.world"),
                    "verbose": "false",
                    "gui": use_gui,
                }.items(),
            ),
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[
                    {"robot_description": robot_description, "use_sim_time": True}
                ],
            ),
            Node(
                package="gazebo_ros",
                executable="spawn_entity.py",
                arguments=[
                    "-topic",
                    "robot_description",
                    "-entity",
                    "spore_patrol_robot",
                    "-x",
                    "-6.5",
                    "-y",
                    "0.0",
                    "-z",
                    "0.02",
                ],
                output="screen",
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=[
                    "-d",
                    str(description_share / "rviz" / "model.rviz"),
                ],
                parameters=[{"use_sim_time": True}],
                condition=IfCondition(use_rviz),
                output="screen",
            ),
        ]
    )
