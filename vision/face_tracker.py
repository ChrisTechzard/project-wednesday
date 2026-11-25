"""Face landmarks, head pose and blink estimation using MediaPipe FaceMesh."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from core.logging import get_logger

MODEL_POINTS = np.array(
    [
        [0.0, 0.0, 0.0],
        [0.0, -330.0, -65.0],
        [-225.0, 170.0, -135.0],
        [225.0, 170.0, -135.0],
        [-150.0, -150.0, -125.0],
    ],
    dtype=np.float64,
)
IMAGE_POINTS = [1, 152, 33, 263, 61]
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
LEFT_IRIS = list(range(468, 473))
RIGHT_IRIS = list(range(473, 478))


@dataclass(frozen=True, slots=True)
class FaceState:
    """Per-frame face tracking output."""

    detected: bool
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    gaze_x: float = 0.5
    gaze_y: float = 0.5
    blink: bool = False
    ear: float = 0.0
    confidence: float = 0.0
    landmarks: Any = None


class FaceTracker:
    """Detect a face and estimate head direction, gaze proxy and blinks."""

    def __init__(self) -> None:
        self._log = get_logger("face")
        self._mesh: Any | None = None

    def _load(self) -> Any:
        if self._mesh is None:
            import mediapipe as mp

            self._mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        return self._mesh

    def process(self, frame_bgr: np.ndarray, blink_threshold: float = 0.22) -> FaceState:
        """Process one BGR frame and return estimated tracking state."""
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = self._load().process(rgb)
        except Exception as exc:
            self._log.warning("Face tracking failed: %s", exc)
            return FaceState(detected=False)

        if not results.multi_face_landmarks:
            return FaceState(detected=False)
        landmarks = results.multi_face_landmarks[0].landmark
        height, width = frame_bgr.shape[:2]

        points = np.array(
            [[landmarks[i].x * width, landmarks[i].y * height] for i in IMAGE_POINTS],
            dtype=np.float64,
        )
        focal = width
        centre = (width / 2.0, height / 2.0)
        camera_matrix = np.array(
            [[focal, 0, centre[0]], [0, focal, centre[1]], [0, 0, 1]], dtype=np.float64
        )
        distortion = np.zeros((4, 1), dtype=np.float64)
        try:
            _, rotation, _ = cv2.solvePnP(MODEL_POINTS, points, camera_matrix, distortion)
            yaw, pitch, roll = (float(value) for value in cv2.Rodrigues(rotation)[0].flatten()[:3])
        except cv2.error:
            yaw = pitch = roll = 0.0

        ear = self._eye_aspect_ratio(landmarks, width, height)
        gaze_x, gaze_y = self._iris_position(landmarks, width, height)
        return FaceState(
            detected=True,
            yaw=float(np.clip(yaw, -1, 1)),
            pitch=float(np.clip(pitch, -1, 1)),
            roll=float(np.clip(roll, -1, 1)),
            gaze_x=gaze_x,
            gaze_y=gaze_y,
            blink=ear < blink_threshold,
            ear=ear,
            confidence=0.9,
            landmarks=landmarks,
        )

    @staticmethod
    def _distance(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.linalg.norm(a - b))

    def _eye_aspect_ratio(self, landmarks: Any, width: int, height: int) -> float:
        def points(indices: list[int]) -> np.ndarray:
            return np.array([[landmarks[i].x * width, landmarks[i].y * height] for i in indices])

        left, right = points(LEFT_EYE), points(RIGHT_EYE)
        left_ear = (self._distance(left[1], left[5]) + self._distance(left[2], left[4])) / max(
            self._distance(left[0], left[3]), 1e-6
        )
        right_ear = (self._distance(right[1], right[5]) + self._distance(right[2], right[4])) / max(
            self._distance(right[0], right[3]), 1e-6
        )
        return float((left_ear + right_ear) / 2.0)

    @staticmethod
    def _iris_position(landmarks: Any, width: int, height: int) -> tuple[float, float]:
        """Return iris centre normalised within the face bounding box."""
        xs = [landmark.x * width for landmark in landmarks]
        ys = [landmark.y * height for landmark in landmarks]
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        if right - left < 1 or bottom - top < 1:
            return 0.5, 0.5
        iris = landmarks[468 + 6] if len(landmarks) > 474 else landmarks[1]
        x = (iris.x * width - left) / (right - left)
        y = (iris.y * height - top) / (bottom - top)
        return float(np.clip(x, 0, 1)), float(np.clip(y, 0, 1))
