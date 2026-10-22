"""
Fisheye and radial lens distortion correction module.
Precomputes undistortion maps using OpenCV to rectify wide-angle lens barrel distortion
at >60 FPS performance using cv2.remap.
"""

from typing import Tuple, Optional
import cv2
import numpy as np


class LensDistortionCorrector:
    """Corrects camera lens radial and tangential distortion."""

    def __init__(self, k1: float = -0.22, k2: float = 0.05, p1: float = 0.0, p2: float = 0.0,
                 focal_scale: float = 0.9, enabled: bool = False):
        self.k1 = k1
        self.k2 = k2
        self.p1 = p1
        self.p2 = p2
        self.focal_scale = focal_scale
        self.enabled = enabled

        self._current_size: Optional[Tuple[int, int]] = None
        self._map1: Optional[np.ndarray] = None
        self._map2: Optional[np.ndarray] = None

    def update_params(self, k1: float, k2: float, enabled: bool = True, focal_scale: float = 0.9) -> None:
        """Update distortion coefficients and invalidate cached remap tables."""
        if (self.k1 != k1 or self.k2 != k2 or self.enabled != enabled or self.focal_scale != focal_scale):
            self.k1 = k1
            self.k2 = k2
            self.enabled = enabled
            self.focal_scale = focal_scale
            self._map1 = None
            self._map2 = None

    def _build_maps(self, width: int, height: int) -> None:
        """Precomputes OpenCV fast remap matrices."""
        fx = width * self.focal_scale
        fy = width * self.focal_scale
        cx = width / 2.0
        cy = height / 2.0

        camera_matrix = np.array([
            [fx, 0, cx],
            [0, fy, cy],
            [0, 0, 1]
        ], dtype=np.float32)

        dist_coeffs = np.array([self.k1, self.k2, self.p1, self.p2], dtype=np.float32)

        new_cam_matrix, _ = cv2.getOptimalNewCameraMatrix(
            camera_matrix, dist_coeffs, (width, height), alpha=1.0, newImgSize=(width, height)
        )

        self._map1, self._map2 = cv2.initUndistortRectifyMap(
            camera_matrix, dist_coeffs, None, new_cam_matrix, (width, height), cv2.CV_16SC2
        )
        self._current_size = (width, height)

    def undistort(self, frame: np.ndarray) -> np.ndarray:
        """Applies fast remap unwarping to input frame."""
        if not self.enabled or frame is None:
            return frame

        h, w = frame.shape[:2]
        if self._map1 is None or self._current_size != (w, h):
            self._build_maps(w, h)

        return cv2.remap(frame, self._map1, self._map2, interpolation=cv2.INTER_LINEAR)
