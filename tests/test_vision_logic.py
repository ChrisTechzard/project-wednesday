"""Pure-logic vision tests that need no camera or user interaction."""

from __future__ import annotations

import time

from vision.dwell import DwellController
from vision.gaze import GazeCalibrator


def test_gaze_calibration_maps_points(tmp_path) -> None:
    calibrator = GazeCalibrator(tmp_path / "calibration.json")
    for ix, iy, sx, sy in [
        (0.1, 0.1, 0.1, 0.1), (0.9, 0.1, 0.9, 0.1),
        (0.1, 0.9, 0.1, 0.9), (0.9, 0.9, 0.9, 0.9),
        (0.5, 0.5, 0.5, 0.5), (0.2, 0.7, 0.2, 0.7),
    ]:
        calibrator.add_sample(ix, iy, sx, sy)
    assert calibrator.compute() is True
    x, y = calibrator.map(0.5, 0.5)
    assert abs(x - 0.5) < 0.05 and abs(y - 0.5) < 0.05
    reloaded = GazeCalibrator(tmp_path / "calibration.json")
    assert reloaded.load() is True


def test_calibration_requires_four_samples(tmp_path) -> None:
    calibrator = GazeCalibrator(tmp_path / "calibration.json")
    calibrator.add_sample(0.1, 0.1, 0.1, 0.1)
    assert calibrator.compute() is False
    assert calibrator.calibrated is False


def test_cancelling_calibration_keeps_the_last_fit(tmp_path) -> None:
    calibrator = GazeCalibrator(tmp_path / "calibration.json")
    for ix, iy, sx, sy in [
        (0.1, 0.1, 0.1, 0.1), (0.9, 0.1, 0.9, 0.1),
        (0.1, 0.9, 0.1, 0.9), (0.9, 0.9, 0.9, 0.9),
    ]:
        calibrator.add_sample(ix, iy, sx, sy)
    assert calibrator.compute() is True

    calibrator.begin()
    calibrator.add_sample(0.5, 0.5, 0.5, 0.5)
    assert calibrator.sample_count == 1
    assert calibrator.calibrated is True

    calibrator.cancel()
    assert calibrator.sample_count == 0
    assert calibrator.calibrated is True


def test_dwell_requires_stable_target() -> None:
    controller = DwellController(dwell_seconds=0.3, radius_px=10)
    first = controller.update(100, 100, True)
    assert first.progress == 0.0
    moved = controller.update(500, 500, True)
    assert moved.progress == 0.0
    time.sleep(0.4)
    done = controller.update(500, 500, True)
    assert done.progress >= 1.0 and done.selected is True
