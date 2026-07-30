from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    package_share = Path(
        get_package_share_directory("spore_patrol_localization")
    )
    config_file = LaunchConfiguration("config_file")
    use_sim_time = LaunchConfiguration("use_sim_time")
    publish_tf = LaunchConfiguration("publish_tf")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value=str(package_share / "config" / "local_ekf.yaml"),
                description="IMU calibration and local EKF parameter file.",
            ),
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument(
                "publish_tf",
                default_value="true",
                description="Let the EKF publish odom to base_footprint.",
            ),
            Node(
                package="spore_patrol_localization",
                executable="imu_bias_calibrator.py",
                name="imu_bias_calibrator",
                output="screen",
                parameters=[
                    config_file,
                    {
                        "use_sim_time": ParameterValue(
                            use_sim_time,
                            value_type=bool,
                        ),
                    },
                ],
            ),
            Node(
                package="robot_localization",
                executable="ekf_node",
                name="ekf_local_filter_node",
                output="screen",
                parameters=[
                    config_file,
                    {
                        "use_sim_time": ParameterValue(
                            use_sim_time,
                            value_type=bool,
                        ),
                        "publish_tf": ParameterValue(
                            publish_tf,
                            value_type=bool,
                        ),
                    },
                ],
            ),
        ]
    )
