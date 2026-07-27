from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
import xacro


def generate_launch_description():
    package_share = Path(get_package_share_directory("spore_patrol_description"))
    robot_description = xacro.process_file(
        str(
            package_share
            / "urdf"
            / "vendor_senior_4wd_bs_preview.urdf.xacro"
        )
    ).toxml()

    return LaunchDescription(
        [
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                parameters=[{"robot_description": robot_description}],
                output="screen",
            ),
            Node(
                package="joint_state_publisher",
                executable="joint_state_publisher",
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
                    str(package_share / "rviz" / "vendor_model_preview.rviz"),
                ],
                output="screen",
            ),
        ]
    )
