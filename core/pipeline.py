"""
Integrated Video Processing Pipeline for Foosball Tracking.
Connects lens distortion correction, homography rectification, HSV detection,
Kalman filter tracking, zone mapping, and event detection into a unified processor.
"""

from dataclasses import dataclass
from typing import Tuple, Optional, List, Dict, Any
import cv2
import numpy as np

from core.fisheye import LensDistortionCorrector
from core.homography import HomographyTransformer
from core.detector import BallDetector, DetectionResult
from core.kalman import FoosballKalmanFilter, KalmanState
from core.zones import TableZones
from core.fsm import EventFSM, GameEvent


@dataclass
class FrameProcessingOutput:
    """Consolidated result output from a single frame processing step."""
    raw_frame_annotated: np.ndarray
    rectified_frame_annotated: np.ndarray
    detection_mask: Optional[np.ndarray]
    kalman_state: KalmanState
    detection_result: DetectionResult
    events: List[GameEvent]
    fps: float
    raw_frame_clean: Optional[np.ndarray] = None


class TrackerPipeline:
    """End-to-end vision and analytics pipeline for vertical 700x1200 table."""

    def __init__(self, config_data: Dict[str, Any]):
        self.config = config_data

        # 1. Lens Distortion Corrector
        fe_cfg = self.config.get("fisheye", {})
        self.fisheye = LensDistortionCorrector(
            k1=float(fe_cfg.get("k1", -0.22)),
            k2=float(fe_cfg.get("k2", 0.05)),
            p1=float(fe_cfg.get("p1", 0.0)),
            p2=float(fe_cfg.get("p2", 0.0)),
            focal_scale=float(fe_cfg.get("focal_scale", 0.9)),
            enabled=bool(fe_cfg.get("enabled", False))
        )

        # 2. Homography Transformer (Vertical: 700 width x 1200 height)
        target_res = self.config.get("target_resolution", [700, 1200])
        self.target_width = target_res[0]
        self.target_height = target_res[1]

        pts = self.config.get("calibration_points", [])
        self.homography = HomographyTransformer(
            target_width=self.target_width,
            target_height=self.target_height,
            points=pts if len(pts) == 4 else None
        )

        # 3. Ball Detector
        cf = self.config.get("contour_filter", {})
        self.detector = BallDetector(
            hsv_bounds=self.config.get("hsv_bounds", {}),
            min_area=float(cf.get("min_area", 40.0)),
            max_area=float(cf.get("max_area", 2500.0)),
            min_circularity=float(cf.get("min_circularity", 0.35)),
            morph_kernel_size=int(cf.get("morph_kernel_size", 3))
        )

        # 4. Kalman Filter
        kf_cfg = self.config.get("kalman", {})
        self.kalman = FoosballKalmanFilter(
            dt=1.0 / 30.0,
            pixels_per_cm=float(self.config.get("pixels_per_cm", 10.0)),
            max_occlusion_frames=int(kf_cfg.get("max_occlusion_frames", 15)),
            motion_trail_length=int(kf_cfg.get("motion_trail_length", 25)),
            process_noise_pos=float(kf_cfg.get("process_noise_pos", 0.01)),
            process_noise_vel=float(kf_cfg.get("process_noise_vel", 5.0)),
            measurement_noise=float(kf_cfg.get("measurement_noise", 1.0))
        )

        # 5. Table Zones
        self.zones = TableZones(self.config.get("zones", {}))

        # 6. Event FSM
        fsm_cfg = self.config.get("fsm", {})
        self.fsm = EventFSM(
            min_shot_speed_kmh=float(fsm_cfg.get("min_shot_speed_kmh", 12.0)),
            goal_lockout_seconds=float(fsm_cfg.get("goal_lockout_seconds", 3.0)),
            pass_timeout_seconds=float(fsm_cfg.get("pass_timeout_seconds", 1.5)),
            possession_min_frames=int(fsm_cfg.get("possession_min_frames", 4))
        )

        self._frame_count: int = 0

    def reset(self) -> None:
        """Resets tracking and state engines."""
        self.kalman.reset()
        self.fsm.reset()
        self._frame_count = 0

    def update_from_config(self, config_data: Dict[str, Any]) -> None:
        """Dynamically applies newly saved configuration parameters."""
        self.config = config_data
        fe_cfg = self.config.get("fisheye", {})
        self.fisheye.update_params(
            k1=float(fe_cfg.get("k1", -0.22)),
            k2=float(fe_cfg.get("k2", 0.05)),
            enabled=bool(fe_cfg.get("enabled", False)),
            focal_scale=float(fe_cfg.get("focal_scale", 0.9))
        )

        pts = self.config.get("calibration_points", [])
        if len(pts) == 4:
            self.homography.set_points(pts)

        self.detector.set_hsv_bounds(self.config.get("hsv_bounds", {}))
        cf = self.config.get("contour_filter", {})
        self.detector.set_filters(
            min_area=float(cf.get("min_area", 40.0)),
            max_area=float(cf.get("max_area", 2500.0)),
            min_circularity=float(cf.get("min_circularity", 0.35))
        )

    def process_frame(self, raw_frame: np.ndarray, timestamp_ms: int, fps: float = 30.0) -> FrameProcessingOutput:
        """Executes full computer vision pipeline on incoming camera frame."""
        self._frame_count += 1
        self.kalman.set_dt(1.0 / max(1.0, fps))

        # Step 1: Lens distortion correction
        undistorted = self.fisheye.undistort(raw_frame)

        # Step 2: Homography perspective rectification (700 x 1200 vertical)
        rectified = self.homography.warp(undistorted)
        if rectified is None or rectified.shape[0] != self.target_height or rectified.shape[1] != self.target_width:
            rectified = np.zeros((self.target_height, self.target_width, 3), dtype=np.uint8)

        # Step 3: Ball detection in rectified top-down space
        predicted_pos = (self.kalman.X[0, 0], self.kalman.X[1, 0]) if self.kalman.is_tracking else None
        det_result = self.detector.detect(rectified, predicted_pos)

        # Step 4: Kalman filter state update
        measurement = det_result.centroid if det_result.found else None
        kalman_state = self.kalman.update(measurement)

        # Step 5: Zone mapping & FSM Event processing
        events = self.fsm.process_frame(
            timestamp_ms=timestamp_ms,
            x=kalman_state.x,
            y=kalman_state.y,
            vx=kalman_state.vx,
            vy=kalman_state.vy,
            speed_kmh=kalman_state.speed_kmh,
            is_tracking=kalman_state.is_tracking,
            zones=self.zones
        )

        # Step 6: Render overlays
        rectified_annotated = self._annotate_rectified(rectified.copy(), det_result, kalman_state)
        raw_annotated = self._annotate_raw(raw_frame.copy(), kalman_state)

        return FrameProcessingOutput(
            raw_frame_annotated=raw_annotated,
            rectified_frame_annotated=rectified_annotated,
            detection_mask=det_result.mask,
            kalman_state=kalman_state,
            detection_result=det_result,
            events=events,
            fps=fps,
            raw_frame_clean=undistorted
        )

    def _annotate_rectified(self, canvas: np.ndarray,
                            det: DetectionResult,
                            ks: KalmanState) -> np.ndarray:
        """Renders zones, motion trail, velocity vectors, and state badges onto vertical canvas."""
        # 1. Draw table zones
        canvas = self.zones.draw_zones(canvas)

        # 2. Draw motion trail
        trail = list(self.kalman.motion_trail)
        for i in range(1, len(trail)):
            alpha = i / max(1, len(trail))
            thickness = max(1, int(3 * alpha))
            color = (int(0 * alpha), int(220 * alpha), int(255 * alpha))
            pt1 = (int(trail[i - 1][0]), int(trail[i - 1][1]))
            pt2 = (int(trail[i][0]), int(trail[i][1]))
            cv2.line(canvas, pt1, pt2, color, thickness)

        # 3. Draw ball state if tracking
        if ks.is_tracking:
            cx, cy = int(ks.x), int(ks.y)

            if ks.is_occluded:
                cv2.circle(canvas, (cx, cy), 12, (0, 220, 255), 2)
                cv2.putText(canvas, f"PREDICTED ({ks.occlusion_frames})", (cx + 15, cy - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 220, 255), 1, cv2.LINE_AA)
            else:
                cv2.circle(canvas, (cx, cy), max(6, int(det.radius)), (0, 255, 0), 2)
                cv2.circle(canvas, (cx, cy), 3, (0, 0, 255), -1)

            # Velocity vector arrow
            if ks.speed_kmh > 2.0:
                arrow_scale = 0.08
                arrow_end = (int(cx + ks.vx * arrow_scale), int(cy + ks.vy * arrow_scale))
                cv2.arrowedLine(canvas, (cx, cy), arrow_end, (0, 255, 255), 2, tipLength=0.3)

            # Speed label badge
            speed_txt = f"{ks.speed_kmh:.1f} km/h"
            cv2.putText(canvas, speed_txt, (cx + 12, cy + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        return canvas

    def _annotate_raw(self, canvas: np.ndarray, ks: KalmanState) -> np.ndarray:
        """Draws the 4 calibration corner vertices and table outline on raw camera frame."""
        pts = self.homography.points
        if len(pts) == 4:
            pts_arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
            cv2.polylines(canvas, [pts_arr], isClosed=True, color=(0, 255, 255), thickness=2)
            corner_labels = ["1:TL", "2:TR", "3:BR", "4:BL"]
            for i, p in enumerate(pts):
                px, py = int(p[0]), int(p[1])
                cv2.circle(canvas, (px, py), 6, (0, 0, 255), -1)
                cv2.putText(canvas, f"{corner_labels[i]}: ({px},{py})", (px + 10, py - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)

        if ks.is_tracking:
            raw_pt = self.homography.inverse_transform_point((ks.x, ks.y))
            if raw_pt:
                rpx, rpy = int(raw_pt[0]), int(raw_pt[1])
                cv2.circle(canvas, (rpx, rpy), 10, (0, 255, 0), 2)
                cv2.circle(canvas, (rpx, rpy), 3, (0, 0, 255), -1)

        return canvas
