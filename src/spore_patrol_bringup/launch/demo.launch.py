from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    sim_share = Path(get_package_share_directory("spore_patrol_sim"))
    use_gui = LaunchConfiguration("gui")
    use_rviz = LaunchConfiguration("rviz")

    return LaunchDescription(
        [
            DeclareLaunchArgument("gui", default_value="true"),
            DeclareLaunchArgument("rviz", default_value="true"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    str(sim_share / "launch" / "sim.launch.py")
                ),
                launch_arguments={"gui": use_gui, "rviz": use_rviz}.items(),
            )
        ]
    )
