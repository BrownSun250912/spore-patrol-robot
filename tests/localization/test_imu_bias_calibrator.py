#!/usr/bin/env python3

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "spore_patrol_localization"
    / "scripts"
    / "imu_bias_calibrator.py"
)
SPEC = importlib.util.spec_from_file_location(
    "imu_bias_calibrator", MODULE_PATH
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
GyroBiasEstimator = MODULE.GyroBiasEstimator


class GyroBiasEstimatorTest(unittest.TestCase):

    def test_estimates_stationary_bias(self):
        estimator = GyroBiasEstimator(1.0, 10, 0.03)
        state = None
        for index in range(21):
            state = estimator.add_sample(
                index * 0.05,
                0.001,
                -0.002,
                0.0008,
            )
        self.assertEqual(state, "completed")
        self.assertTrue(estimator.ready)
        self.assertAlmostEqual(estimator.bias[0], 0.001)
        self.assertAlmostEqual(estimator.bias[1], -0.002)
        self.assertAlmostEqual(estimator.bias[2], 0.0008)

    def test_motion_restarts_calibration(self):
        estimator = GyroBiasEstimator(0.5, 5, 0.03)
        for index in range(5):
            estimator.add_sample(index * 0.05, 0.0, 0.0, 0.001)
        state = estimator.add_sample(0.3, 0.0, 0.0, 0.2)
        self.assertEqual(state, "motion_reset")
        self.assertFalse(estimator.ready)
        self.assertEqual(estimator.sample_count, 0)

        states = []
        for index in range(12):
            state = estimator.add_sample(
                1.0 + index * 0.05,
                0.0,
                0.0,
                0.001,
            )
            states.append(state)
        self.assertIn("completed", states)
        self.assertTrue(estimator.ready)

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            GyroBiasEstimator(0.0, 10, 0.03)
        with self.assertRaises(ValueError):
            GyroBiasEstimator(1.0, 0, 0.03)
        with self.assertRaises(ValueError):
            GyroBiasEstimator(1.0, 10, 0.0)


if __name__ == "__main__":
    unittest.main()
