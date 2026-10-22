"""
Homography Perspective Transformation Module.
Resolves perspective distortion caused by off-center camera placement by computing
a 3x3 transformation matrix M mapping physical table corners to a normalized 1200x700 plane.
"""

from typing import List, Tuple, Optional
import cv2
import numpy as np


class HomographyTransformer:
    """Manages perspective transformation from camera view to canonical 1200x700 table view."""

    def __init__(self, target_width: int = 1200, target_height: int = 700,
                 points: Optional[List[List[float]]] = None):
        self.target_width = target_width
        self.target_height = target_height
        self.points: List[Tuple[float, float]] = []
        self.matrix: Optional[np.ndarray] = None
        self.inv_matrix: Optional[np.ndarray] = None

        self.dst_points = np.array([
            [0.0, 0.0],
            [float(self.target_width), 0.0],
            [float(self.target_width), float(self.target_height)],
            [0.0, float(self.target_height)]
        ], dtype=np.float32)

        if points and len(points) == 4:
            self.set_points(points)

    def set_points(self, points: List[List[float]]) -> bool:
        """Sets the 4 source corner points in clockwise order: TL, TR, BR, BL."""
        if len(points) != 4:
            return False

        src = np.array(points, dtype=np.float32)
        try:
            M = cv2.getPerspectiveTransform(src, self.dst_points)
            inv_M = np.linalg.inv(M)
            self.matrix = M
            self.inv_matrix = inv_M
            self.points = [(float(p[0]), float(p[1])) for p in points]
            return True
        except Exception as e:
            print(f"[HomographyTransformer] Error computing matrix: {e}")
            return False

    def is_calibrated(self) -> bool:
        """Returns True if a valid 3x3 transformation matrix has been computed."""
        return self.matrix is not None

    def warp(self, frame: np.ndarray) -> np.ndarray:
        """Warps the raw input frame into the canonical 1200x700 top-down table view."""
        if self.matrix is None or frame is None:
            return frame
        return cv2.warpPerspective(
            frame,
            self.matrix,
            (self.target_width, self.target_height),
            flags=cv2.INTER_LINEAR
        )

    def transform_point(self, pt: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        """Maps a point (x, y) from distorted camera frame to canonical table space."""
        if self.matrix is None:
            return None
        src_pt = np.array([[[pt[0], pt[1]]]], dtype=np.float32)
        dst_pt = cv2.perspectiveTransform(src_pt, self.matrix)
        return float(dst_pt[0][0][0]), float(dst_pt[0][0][1])

    def inverse_transform_point(self, pt: Tuple[float, float]) -> Optional[Tuple[float, float]]:
        """Maps a point (x, y) from canonical table space back to distorted camera frame."""
        if self.inv_matrix is None:
            return None
        src_pt = np.array([[[pt[0], pt[1]]]], dtype=np.float32)
        dst_pt = cv2.perspectiveTransform(src_pt, self.inv_matrix)
        return float(dst_pt[0][0][0]), float(dst_pt[0][0][1])
