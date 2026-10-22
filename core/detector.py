"""
Ball Detection Engine for Foosball Tracking.
Extracts high-contrast ball candidates using dual-range HSV color thresholding,
morphological filters, shape metrics (area and circularity), and spatial centroid moments.
"""

from dataclasses import dataclass
from typing import Tuple, Optional, List, Dict, Any
import cv2
import numpy as np


@dataclass
class DetectionResult:
    """Encapsulates ball detection output for a single frame."""
    found: bool
    centroid: Optional[Tuple[float, float]] = None
    radius: float = 0.0
    contour: Optional[np.ndarray] = None
    mask: Optional[np.ndarray] = None
    circularity: float = 0.0
    area: float = 0.0


class BallDetector:
    """Detects foosball centroid using HSV color thresholding and shape geometry."""

    def __init__(self,
                 hsv_bounds: Optional[Dict[str, Any]] = None,
                 min_area: float = 40.0,
                 max_area: float = 2500.0,
                 min_circularity: float = 0.35,
                 morph_kernel_size: int = 3):
        
        self.min_area = min_area
        self.max_area = max_area
        self.min_circularity = min_circularity
        self.morph_kernel_size = morph_kernel_size

        # Default HSV settings for Red / Orange ball
        self.dual_range = True
        self.lower1 = np.array([0, 60, 40], dtype=np.uint8)
        self.upper1 = np.array([15, 255, 255], dtype=np.uint8)
        self.lower2 = np.array([165, 60, 40], dtype=np.uint8)
        self.upper2 = np.array([180, 255, 255], dtype=np.uint8)

        if hsv_bounds:
            self.set_hsv_bounds(hsv_bounds)

        self._morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (self.morph_kernel_size, self.morph_kernel_size)
        )

    def set_hsv_bounds(self, bounds: Dict[str, Any]) -> None:
        """Configures HSV color boundary thresholds."""
        self.dual_range = bounds.get("dual_range", True)
        self.lower1 = np.array(bounds.get("lower1", [0, 60, 40]), dtype=np.uint8)
        self.upper1 = np.array(bounds.get("upper1", [15, 255, 255]), dtype=np.uint8)
        if self.dual_range:
            self.lower2 = np.array(bounds.get("lower2", [165, 60, 40]), dtype=np.uint8)
            self.upper2 = np.array(bounds.get("upper2", [180, 255, 255]), dtype=np.uint8)

    def set_filters(self, min_area: float, max_area: float, min_circularity: float) -> None:
        self.min_area = min_area
        self.max_area = max_area
        self.min_circularity = min_circularity

    def get_mask(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Generates binary HSV mask after morphological cleaning."""
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        mask1 = cv2.inRange(hsv, self.lower1, self.upper1)
        if self.dual_range:
            mask2 = cv2.inRange(hsv, self.lower2, self.upper2)
            mask = cv2.bitwise_or(mask1, mask2)
        else:
            mask = mask1

        # Morphological opening (erosion then dilation) strips high-frequency pixel noise
        opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._morph_kernel)
        # Morphological closing fills interior holes
        closed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, self._morph_kernel)
        return closed

    def detect(self, frame_bgr: np.ndarray,
               predicted_pos: Optional[Tuple[float, float]] = None) -> DetectionResult:
        """
        Executes contour extraction and identifies optimal ball candidate.
        If predicted_pos is supplied (from Kalman filter), prioritizes valid candidates
        near the predicted trajectory.
        """
        if frame_bgr is None:
            return DetectionResult(found=False)

        mask = self.get_mask(frame_bgr)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates: List[Tuple[float, float, float, float, np.ndarray, float]] = []
        # Item: (score, cx, cy, radius, contour, circularity)

        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < self.min_area or area > self.max_area:
                continue

            perimeter = float(cv2.arcLength(cnt, True))
            if perimeter <= 0:
                continue

            circularity = 4.0 * np.pi * area / (perimeter * perimeter)
            if circularity < self.min_circularity:
                continue

            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue

            cx = float(M["m10"] / M["m00"])
            cy = float(M["m01"] / M["m00"])
            (_, _), radius = cv2.minEnclosingCircle(cnt)

            # Score candidate based on circularity, area plausibility, and proximity
            # Base score: higher circularity is better
            score = circularity * 100.0

            if predicted_pos is not None:
                dist = np.hypot(cx - predicted_pos[0], cy - predicted_pos[1])
                # Proximity bonus / penalty
                if dist < 120.0:
                    score += max(0.0, 100.0 - dist)
                else:
                    score -= (dist - 120.0) * 0.5

            candidates.append((score, cx, cy, float(radius), cnt, circularity, area))

        if not candidates:
            return DetectionResult(found=False, mask=mask)

        # Sort descending by score
        candidates.sort(key=lambda item: item[0], reverse=True)
        best = candidates[0]

        return DetectionResult(
            found=True,
            centroid=(best[1], best[2]),
            radius=best[3],
            contour=best[4],
            mask=mask,
            circularity=best[5],
            area=best[6]
        )
