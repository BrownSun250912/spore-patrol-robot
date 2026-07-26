from glob import glob
import os

from setuptools import find_packages, setup


package_name = "spore_patrol_base_driver"


setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=("test",)),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        (
            os.path.join("share", package_name, "config"),
            glob("config/*.yaml"),
        ),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.launch.py"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Spore Patrol Team",
    maintainer_email="team@example.com",
    description="ROS 2 serial driver for the WHEELTEC C50X STM32 chassis.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "base_driver_node = "
            "spore_patrol_base_driver.base_driver_node:main",
        ],
    },
)
