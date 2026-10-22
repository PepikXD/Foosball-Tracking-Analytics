"""
Kalman Filter State Estimation Engine for Foosball Tracking.
Implements a 4D continuous linear kinematic model [x, y, vx, vy]^T to smooth visual jitter,
estimate real-time ball velocity vectors, and bridge player rod occlusions up to 15 frames.
"""

from collections import deque
from dataclasses import dataclass
from typing import Tuple, Optional, Deque, List
import numpy as np


@dataclass
class KalmanState:
    """Represents the estimated physical state of the foosball target."""
    x: float
    y: float
    vx: float
    vy: float
    speed_kmh: float
    is_tracking: bool
    is_occluded: bool
    occlusion_frames: int


class FoosballKalmanFilter:
    """Linear Kalman filter tracking ball centroid and velocity vectors."""

    def __init__(self,
                 dt: float = 1.0 / 30.0,
                 pixels_per_cm: float = 10.0,
                 max_occlusion_frames: int = 15,
                 motion_trail_length: int = 25,
                 process_noise_pos: float = 0.05,
                 process_noise_vel: float = 5.0,
                 measurement_noise: float = 1.0):

        self.dt = dt
        self.pixels_per_cm = pixels_per_cm
        self.max_occlusion_frames = max_occlusion_frames
        self.motion_trail_length = motion_trail_length

        # State transition matrix F
        self.F = np.array([
            [1.0, 0.0, self.dt, 0.0],
            [0.0, 1.0, 0.0, self.dt],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]
        ], dtype=np.float64)

        # Measurement matrix H
        self.H = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0]
        ], dtype=np.float64)

        # Process noise covariance Q
        q_pos = process_noise_pos
        q_vel = process_noise_vel
        self.Q = np.array([
            [q_pos, 0.0, 0.0, 0.0],
            [0.0, q_pos, 0.0, 0.0],
            [0.0, 0.0, q_vel, 0.0],
            [0.0, 0.0, 0.0, q_vel]
        ], dtype=np.float64)

        # Measurement noise covariance R
        self.R = np.eye(2, dtype=np.float64) * measurement_noise

        # State vector [x, y, vx, vy]^T and covariance matrix P
        self.X = np.zeros((4, 1), dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 500.0

        self.is_tracking: bool = False
        self.occlusion_frames: int = 0
        self.motion_trail: Deque[Tuple[float, float]] = deque(maxlen=self.motion_trail_length)

    def set_dt(self, dt: float) -> None:
        """Dynamically update time step between frames (e.g., from camera FPS)."""
        self.dt = max(1e-4, dt)
        self.F[0, 2] = self.dt
        self.F[1, 3] = self.dt

    def reset(self) -> None:
        """Resets filter state when tracking is lost."""
        self.X = np.zeros((4, 1), dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 500.0
        self.is_tracking = False
        self.occlusion_frames = 0
        self.motion_trail.clear()

    def predict(self) -> Tuple[float, float]:
        """A priori state prediction: X_k|k-1 = F * X_k-1."""
        if not self.is_tracking:
            return 0.0, 0.0

        self.X = self.F @ self.X
        self.P = self.F @ self.P @ self.F.T + self.Q
        return float(self.X[0, 0]), float(self.X[1, 0])

    def update(self, measurement: Optional[Tuple[float, float]]) -> KalmanState:
        """
        Executes filter cycle:
        - If measurement present: Predict -> Correct -> Reset occlusion counter
        - If measurement absent: Predict -> Increment occlusion counter
        """
        if measurement is not None:
            mx, my = measurement
            z = np.array([[mx], [my]], dtype=np.float64)

            if not self.is_tracking:
                # Initialize state with incoming measurement
                self.X = np.array([[mx], [my], [0.0], [0.0]], dtype=np.float64)
                self.P = np.eye(4, dtype=np.float64) * 10.0
                self.is_tracking = True
                self.occlusion_frames = 0
            else:
                # Prediction step
                self.X = self.F @ self.X
                self.P = self.F @ self.P @ self.F.T + self.Q

                # Measurement update step
                y = z - (self.H @ self.X)
                S = self.H @ self.P @ self.H.T + self.R
                K = self.P @ self.H.T @ np.linalg.inv(S)

                self.X = self.X + (K @ y)
                I = np.eye(4, dtype=np.float64)
                self.P = (I - (K @ self.H)) @ self.P

                self.occlusion_frames = 0

            self.motion_trail.append((float(self.X[0, 0]), float(self.X[1, 0])))
            is_occluded = False

        else:
            # Occlusion handling
            if self.is_tracking:
                self.X = self.F @ self.X
                self.P = self.F @ self.P @ self.F.T + self.Q
                self.occlusion_frames += 1

                if self.occlusion_frames <= self.max_occlusion_frames:
                    self.motion_trail.append((float(self.X[0, 0]), float(self.X[1, 0])))
                    is_occluded = True
                else:
                    self.is_tracking = False
                    is_occluded = True
            else:
                is_occluded = True

        x = float(self.X[0, 0])
        y = float(self.X[1, 0])
        vx = float(self.X[2, 0])
        vy = float(self.X[3, 0])

        # Velocity magnitude in pixels / sec:
        # State velocities vx, vy are in pixels / sec (because F has dt)
        pixel_speed_sec = np.hypot(vx, vy)
        # Convert to cm/sec, then m/sec, then km/h:
        # speed_kmh = (pixel_speed_sec / pixels_per_cm) * (1 / 100) * 3.6
        speed_kmh = (pixel_speed_sec / max(1.0, self.pixels_per_cm)) * 0.036

        return KalmanState(
            x=x,
            y=y,
            vx=vx,
            vy=vy,
            speed_kmh=speed_kmh if self.is_tracking else 0.0,
            is_tracking=self.is_tracking,
            is_occluded=is_occluded,
            occlusion_frames=self.occlusion_frames
        )
