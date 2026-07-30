from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
import xacro


def generate_launch_description():
    description_share = Path(
        get_package_share_directory("spore_patrol_description")
    )
    driver_share = Path(
        get_package_share_directory("spore_patrol_base_driver")
    )
    lidar_share = Path(
        get_package_share_directory("spore_patrol_lidar")
    )
    robot_description = xacro.process_file(
        str(description_share / "urdf" / "spore_patrol_robot.urdf.xacro")
    ).toxml()

    port = LaunchConfiguration("port")
    lidar_port = LaunchConfiguration("lidar_port")
    use_lidar = LaunchConfiguration("lidar")
    use_rviz = LaunchConfiguration("rviz")
    base_publish_tf = LaunchConfiguration("base_publish_tf")

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
            DeclareLaunchArgument(
                "lidar",
                default_value="false",
                description="Start the YDLIDAR X3 Pro driver.",
            ),
            DeclareLaunchArgument(
                "lidar_port",
                default_value="/dev/ydlidar",
                description="YDLIDAR CP210x serial device.",
            ),
            DeclareLaunchArgument(
                "base_publish_tf",
                default_value="true",
                description=(
                    "Publish odom to base_footprint from the base driver. "
                    "Set false when robot_localization owns that TF."
                ),
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
                    {
                        "port": port,
                        "publish_tf": ParameterValue(
                            base_publish_tf,
                            value_type=bool,
                        ),
                    },
                ],
            ),
            Node(
                package="ydlidar_ros2_driver",
                executable="ydlidar_ros2_driver_node",
                name="ydlidar_ros2_driver_node",
                condition=IfCondition(use_lidar),
                output="screen",
                emulate_tty=True,
                parameters=[
                    str(lidar_share / "config" / "x3_pro.yaml"),
                    {"port": lidar_port},
                ],
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                arguments=[
                    "-d",
                    str(description_share / "rviz" / "model.rviz"),
                ],
                # Prefer Mesa on this hybrid-graphics laptop. Otherwise RViz
                # may select an unavailable NVIDIA GLX provider and fail to
                # create its OpenGL context.
                additional_env={"__GLX_VENDOR_LIBRARY_NAME": "mesa"},
                condition=IfCondition(use_rviz),
                output="screen",
            ),
        ]
    )
