import math

import pytest

from spore_patrol_base_driver.motion_limits import move_toward
from spore_patrol_base_driver.odometry import PlanarOdometry


def test_integrates_straight_motion():
    odom = PlanarOdometry()
    for _ in range(100):
        odom.update(0.1, 0.0, 0.0, 0.1)
    assert odom.x == pytest.approx(1.0)
    assert odom.y == pytest.approx(0.0)
    assert odom.yaw == pytest.approx(0.0)


def test_integrates_full_rotation():
    odom = PlanarOdometry()
    dt = 0.05
    wz = math.pi / 2.0
    for _ in range(80):
        odom.update(0.0, 0.0, wz, dt)
    assert odom.x == pytest.approx(0.0)
    assert odom.y == pytest.approx(0.0)
    assert odom.yaw == pytest.approx(0.0, abs=1e-12)


def test_move_toward_respects_rate_limit_without_overshoot():
    assert move_toward(0.0, 1.0, 0.2) == pytest.approx(0.2)
    assert move_toward(0.5, 0.0, 0.2) == pytest.approx(0.3)
    assert move_toward(0.1, 0.0, 0.2) == pytest.approx(0.0)
