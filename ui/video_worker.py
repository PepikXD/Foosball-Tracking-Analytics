"""
Asynchronous Video Capture and Processing Worker Thread.
Runs the computer vision pipeline inside a dedicated QThread to ensure 60 FPS UI responsiveness.
Emits thread-safe Qt signals with processed QImages, telemetry metrics, and discrete match events.
"""

import time
from typing import Optional, Dict, Any
import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from core.pipeline import TrackerPipeline, FrameProcessingOutput
from core.fsm import GameEvent


def cv_mat_to_qimage(mat: np.ndarray) -> QImage:
    """Converts OpenCV BGR or grayscale image to PyQt6 QImage."""
    if mat is None:
        return QImage()
    h, w = mat.shape[:2]
    if len(mat.shape) == 2:
        # Grayscale
        bytes_per_line = w
        return QImage(mat.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8).copy()
    else:
        # BGR to RGB
        rgb = cv2.cvtColor(mat, cv2.COLOR_BGR2RGB)
        bytes_per_line = 3 * w
        return QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()


class VideoWorker(QThread):
    """Worker thread running continuous frame capture and OpenCV processing loop."""

    # Signals
    frame_ready = pyqtSignal(QImage, QImage, QImage, QImage)  # rectified, raw, mask, clean_raw
    event_detected = pyqtSignal(object)                      # GameEvent
    telemetry_updated = pyqtSignal(dict)                     # Metrics dictionary
    playback_state_changed = pyqtSignal(bool, float, float)  # is_playing, current_sec, total_sec

    def __init__(self, pipeline: TrackerPipeline, source_path: str = "", camera_index: int = 0, is_file: bool = True):
        super().__init__()
        self.pipeline = pipeline
        self.source_path = source_path
        self.camera_index = camera_index
        self.is_file = is_file

        self._running: bool = True
        self._paused: bool = False
        self._loop: bool = True
        self._playback_speed: float = 1.0
        self._seek_to_frame: Optional[int] = None
        self._force_single_step: bool = False
        self._force_reprocess: bool = False
        self._last_raw_mat: Optional[np.ndarray] = None
        self._cap: Optional[cv2.VideoCapture] = None

    def set_source(self, source_path: str = "", camera_index: int = 0, is_file: bool = True) -> None:
        """Switches video input stream."""
        self.source_path = source_path
        self.camera_index = camera_index
        self.is_file = is_file
        self.pipeline.reset()
        self._last_raw_mat = None
        self._force_single_step = True

        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def toggle_pause(self) -> bool:
        self._paused = not self._paused
        if not self._paused:
            self._force_single_step = False
        return self._paused

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if not self._paused:
            self._force_single_step = False

    def is_paused(self) -> bool:
        return self._paused

    def step_frame(self, delta: int = 1) -> None:
        """Advances or steps back by delta frames and renders immediately."""
        if self._cap and self.is_file:
            cur = self._cap.get(cv2.CAP_PROP_POS_FRAMES)
            self._seek_to_frame = max(0, int(cur + delta))
            self._force_single_step = True

    def seek_position(self, progress_pct: float) -> None:
        """Seeks to relative position [0.0, 1.0] in video file."""
        if self._cap and self.is_file:
            total_frames = self._cap.get(cv2.CAP_PROP_FRAME_COUNT)
            target = int(max(0.0, min(1.0, progress_pct)) * total_frames)
            self._seek_to_frame = target
            self._force_single_step = True

    def request_refresh(self) -> None:
        """Requests pipeline to re-process and emit the current frame while paused."""
        self._force_reprocess = True

    def set_playback_speed(self, speed: float) -> None:
        self._playback_speed = max(0.1, min(5.0, speed))

    def stop(self) -> None:
        self._running = False
        self.wait(2000)

    def run(self) -> None:
        """Main processing thread loop."""
        while self._running:
            # Open video source if needed
            if self._cap is None or not self._cap.isOpened():
                if self.is_file and self.source_path:
                    self._cap = cv2.VideoCapture(self.source_path)
                else:
                    self._cap = cv2.VideoCapture(self.camera_index)

                if not self._cap.isOpened():
                    time.sleep(0.5)
                    continue

            fps = self._cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0 or np.isnan(fps):
                fps = 30.0

            total_frames = self._cap.get(cv2.CAP_PROP_FRAME_COUNT) if self.is_file else 0.0
            total_sec = (total_frames / fps) if (self.is_file and fps > 0) else 0.0

            frame_interval = 1.0 / (fps * self._playback_speed)
            last_frame_time = time.time()

            while self._running and self._cap is not None and self._cap.isOpened():
                if self._seek_to_frame is not None:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._seek_to_frame)
                    self._seek_to_frame = None
                    self._force_single_step = True

                if self._paused and not self._force_single_step and not self._force_reprocess:
                    time.sleep(0.02)
                    continue

                t0 = time.time()

                if self._force_reprocess and self._last_raw_mat is not None:
                    self._force_reprocess = False
                    raw_frame = self._last_raw_mat.copy()
                    ret = True
                else:
                    self._force_single_step = False
                    self._force_reprocess = False
                    ret, raw_frame = self._cap.read()
                    if ret and raw_frame is not None:
                        self._last_raw_mat = raw_frame.copy()

                if not ret or raw_frame is None:
                    if self.is_file and self._loop:
                        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        self.pipeline.reset()
                        continue
                    else:
                        break

                current_frame_pos = self._cap.get(cv2.CAP_PROP_POS_FRAMES)
                current_sec = (current_frame_pos / fps) if fps > 0 else 0.0
                timestamp_ms = int(current_sec * 1000)

                # Execute pipeline processing
                output: FrameProcessingOutput = self.pipeline.process_frame(
                    raw_frame=raw_frame,
                    timestamp_ms=timestamp_ms,
                    fps=fps
                )

                # Emit detected match events
                for ev in output.events:
                    self.event_detected.emit(ev)

                # Emit telemetry dictionary
                ks = output.kalman_state
                poss_a, poss_b = self.pipeline.fsm.get_possession_split()
                telemetry = {
                    "ball_x": ks.x,
                    "ball_y": ks.y,
                    "speed_kmh": ks.speed_kmh,
                    "is_tracking": ks.is_tracking,
                    "is_occluded": ks.is_occluded,
                    "occlusion_frames": ks.occlusion_frames,
                    "current_rod": self.pipeline.fsm.current_possession_rod,
                    "current_team": self.pipeline.fsm.current_possession_team,
                    "possession_a": poss_a,
                    "possession_b": poss_b,
                    "fps": output.fps,
                    "current_sec": current_sec,
                    "total_sec": total_sec,
                }
                self.telemetry_updated.emit(telemetry)

                # Convert frames to QImages and emit to UI
                q_rect = cv_mat_to_qimage(output.rectified_frame_annotated)
                q_raw = cv_mat_to_qimage(output.raw_frame_annotated)
                q_mask = cv_mat_to_qimage(output.detection_mask) if output.detection_mask is not None else QImage()
                clean_mat = output.raw_frame_clean if output.raw_frame_clean is not None else raw_frame
                q_clean = cv_mat_to_qimage(clean_mat)

                self.frame_ready.emit(q_rect, q_raw, q_mask, q_clean)
                self.playback_state_changed.emit(not self._paused, current_sec, total_sec)

                # Sleep to match target framerate pacing when playing
                if not self._paused:
                    elapsed = time.time() - t0
                    sleep_time = max(0.001, frame_interval - elapsed)
                    time.sleep(sleep_time)

        if self._cap is not None:
            self._cap.release()
            self._cap = None
