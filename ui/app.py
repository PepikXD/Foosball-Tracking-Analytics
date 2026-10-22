"""
Main PyQt6 Application Window for Foosball Tracking & Player Analytics.
Coordinates the background video processing worker thread, user configuration,
SQLite persistence, and tabbed dashboard interface.
"""

import os
from typing import Optional, Dict, Any
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QStatusBar,
    QFileDialog, QMessageBox, QInputDialog
)

from core.config import ConfigManager
from core.database import DatabaseManager
from core.pipeline import TrackerPipeline
from core.fsm import GameEvent, EventType
from ui.video_worker import VideoWorker
from ui.dashboard_tab import DashboardTab
from ui.calibration_tab import CalibrationTab
from ui.hsv_tuner_tab import HSVTunerTab
from ui.fisheye_tab import FisheyeTab
from ui.summary_tab import SummaryTab
from ui.players_tab import PlayersTab


DARK_STYLE = """
QMainWindow {
    background-color: #090d16;
}
QTabWidget::pane {
    border: 1px solid #1e293b;
    background-color: #0f172a;
    border-radius: 6px;
}
QTabBar::tab {
    background-color: #1e293b;
    color: #94a3b8;
    font-weight: bold;
    padding: 8px 16px;
    margin-right: 4px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background-color: #0284c7;
    color: #ffffff;
}
QTabBar::tab:hover:!selected {
    background-color: #334155;
    color: #f8fafc;
}
QStatusBar {
    background-color: #1e293b;
    color: #94a3b8;
    font-size: 11px;
}
QMenuBar {
    background-color: #1e293b;
    color: #f8fafc;
    font-weight: bold;
}
QMenuBar::item:selected {
    background-color: #0284c7;
}
QMenu {
    background-color: #1e293b;
    color: #f8fafc;
    border: 1px solid #334155;
}
QMenu::item:selected {
    background-color: #0284c7;
}
"""


class MainWindow(QMainWindow):
    """Primary application window coordinating vision worker and tabs."""

    def __init__(self, config_manager: ConfigManager, db_manager: DatabaseManager):
        super().__init__()
        self.cfg = config_manager
        self.db = db_manager

        self.setWindowTitle("Foosball Tracking & Player Analytics")
        self.resize(1360, 880)
        self.setStyleSheet(DARK_STYLE)

        # Initialize Pipeline
        self.pipeline = TrackerPipeline(self.cfg.data)

        # Active Match Session ID in Database
        self.active_match_id: Optional[int] = None
        self.live_score_a: int = 0
        self.live_score_b: int = 0

        self._init_menu()
        self._init_tabs()
        self._init_worker()

    def _init_menu(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("File")

        act_open = QAction("Open Video File...", self)
        act_open.triggered.connect(self._open_file_dialog)
        file_menu.addAction(act_open)

        act_cam = QAction("Connect Webcam...", self)
        act_cam.triggered.connect(self._select_webcam_dialog)
        file_menu.addAction(act_cam)

        file_menu.addSeparator()

        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Presets Menu
        preset_menu = menubar.addMenu("Presets")

        act_phone = QAction("Phone Camera (2016_0126_042510_001.MOV)", self)
        act_phone.triggered.connect(lambda: self._apply_preset_key("phone_camera_2016_0126"))
        preset_menu.addAction(act_phone)

        act_action = QAction("Action Camera Fisheye (2016_0127_045904_001.MOV)", self)
        act_action.triggered.connect(lambda: self._apply_preset_key("action_camera_2016_0127"))
        preset_menu.addAction(act_action)

        # Help Menu
        help_menu = menubar.addMenu("Help")
        act_about = QAction("About & Documentation", self)
        act_about.triggered.connect(self._show_about_dialog)
        help_menu.addAction(act_about)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Initializing video pipeline...")

    def _init_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # 1. Dashboard Tab
        self.dashboard_tab = DashboardTab(self)
        self.dashboard_tab.pause_toggled.connect(self._on_pause_toggled)
        self.dashboard_tab.seek_requested.connect(self._on_seek_requested)
        self.dashboard_tab.speed_changed.connect(self._on_speed_changed)
        self.dashboard_tab.score_override.connect(self._on_score_override)
        self.dashboard_tab.match_started.connect(self._on_match_started)
        self.dashboard_tab.match_finished.connect(self._on_match_finished)
        self.tabs.addTab(self.dashboard_tab, "Live Match Dashboard")

        # 2. Calibration Tab
        self.calibration_tab = CalibrationTab(self)
        self.calibration_tab.set_initial_points(self.cfg.get("calibration_points", []))
        self.calibration_tab.calibration_saved.connect(self._on_calibration_saved)
        self.calibration_tab.live_calibration_updated.connect(self._on_live_calibration_updated)
        self.tabs.addTab(self.calibration_tab, "Perspective Calibration")

        # 3. HSV Color Tuner Tab
        self.hsv_tab = HSVTunerTab(self)
        self.hsv_tab.set_hsv_bounds(self.cfg.get("hsv_bounds", {}))
        self.hsv_tab.hsv_bounds_changed.connect(self._on_hsv_bounds_changed)
        self.hsv_tab.contour_filters_changed.connect(self._on_contour_filters_changed)
        self.hsv_tab.save_requested.connect(self._on_hsv_saved)
        self.tabs.addTab(self.hsv_tab, "HSV Color Tuner")

        # 4. Fisheye Lens Tab
        self.fisheye_tab = FisheyeTab(self)
        fe_cfg = self.cfg.get("fisheye", {})
        self.fisheye_tab.chk_enable.setChecked(bool(fe_cfg.get("enabled", False)))
        self.fisheye_tab.s_k1.setValue(int(float(fe_cfg.get("k1", -0.22)) * 100))
        self.fisheye_tab.s_k2.setValue(int(float(fe_cfg.get("k2", 0.05)) * 100))
        self.fisheye_tab.s_focal.setValue(int(float(fe_cfg.get("focal_scale", 0.9)) * 100))
        self.fisheye_tab.distortion_changed.connect(self._on_distortion_changed)
        self.fisheye_tab.save_requested.connect(self._on_distortion_saved)
        self.tabs.addTab(self.fisheye_tab, "Fisheye Distortion")

        # 5. Match Summary Tab
        self.summary_tab = SummaryTab(self.db, self)
        self.tabs.addTab(self.summary_tab, "Match Analytics & CSV")

        # 6. Players Tab
        self.players_tab = PlayersTab(self.db, self)
        self.tabs.addTab(self.players_tab, "Players & Leaderboard")

    def _init_worker(self) -> None:
        source_path = self.cfg.get("video_path", "")
        cam_idx = self.cfg.get("camera_index", 0)
        is_file = (self.cfg.get("source_type", "file") == "file")

        self.worker = VideoWorker(
            pipeline=self.pipeline,
            source_path=source_path,
            camera_index=cam_idx,
            is_file=is_file
        )

        self.worker.frame_ready.connect(self._on_frames_ready)
        self.worker.event_detected.connect(self._on_event_detected)
        self.worker.telemetry_updated.connect(self._on_telemetry_updated)
        self.worker.playback_state_changed.connect(self._on_playback_state_changed)

        self.worker.start()
        source_label = os.path.basename(source_path) if is_file else f"Webcam #{cam_idx}"
        self.status_bar.showMessage(f"Streaming from: {source_label}")

    # -------------------------------------------------------------
    # Worker Thread Signal Slots
    # -------------------------------------------------------------
    def _on_frames_ready(self, q_rect, q_raw, q_mask) -> None:
        current_tab_idx = self.tabs.currentIndex()

        if current_tab_idx == 0:
            self.dashboard_tab.update_frame(q_rect, q_raw, q_mask)
        elif current_tab_idx == 1:
            self.calibration_tab.update_frames(q_rect, q_raw)
        elif current_tab_idx == 2:
            self.hsv_tab.update_views(q_rect, q_mask)
        elif current_tab_idx == 3:
            self.fisheye_tab.update_frame(q_raw)

    def _on_telemetry_updated(self, telemetry: Dict[str, Any]) -> None:
        self.dashboard_tab.update_telemetry(telemetry)

    def _on_playback_state_changed(self, is_playing: bool, cur_s: float, tot_s: float) -> None:
        self.dashboard_tab.update_playback_state(is_playing, cur_s, tot_s)

    def _on_event_detected(self, event: GameEvent) -> None:
        # 1. Update live ticker in dashboard
        self.dashboard_tab.add_event(event)

        # 2. Update scores if Goal event
        if event.event_type == EventType.GOAL:
            if event.team == "A":
                self.live_score_a += 1
            elif event.team == "B":
                self.live_score_b += 1
            self.dashboard_tab.set_scores(self.live_score_a, self.live_score_b)

            if self.active_match_id is not None:
                self.db.update_match_score(self.active_match_id, self.live_score_a, self.live_score_b)

        # 3. Log event into SQLite database if match is running
        if self.active_match_id is not None:
            self.db.log_event(self.active_match_id, event)

    # -------------------------------------------------------------
    # Dashboard Control Slots
    # -------------------------------------------------------------
    def _on_pause_toggled(self) -> None:
        self.worker.toggle_pause()

    def _on_seek_requested(self, pct: float) -> None:
        self.worker.seek_position(pct)

    def _on_speed_changed(self, speed: float) -> None:
        self.worker.set_playback_speed(speed)

    def _on_score_override(self, team: str, delta: int) -> None:
        if team == "A":
            self.live_score_a = max(0, self.live_score_a + delta)
        else:
            self.live_score_b = max(0, self.live_score_b + delta)

        self.dashboard_tab.set_scores(self.live_score_a, self.live_score_b)
        if self.active_match_id is not None:
            self.db.update_match_score(self.active_match_id, self.live_score_a, self.live_score_b)

    def _on_match_started(self, team_a: str, team_b: str) -> None:
        src = self.worker.source_path if self.worker.is_file else f"Webcam {self.worker.camera_index}"
        self.live_score_a = 0
        self.live_score_b = 0
        self.dashboard_tab.set_scores(0, 0)
        self.active_match_id = self.db.start_match(team_a, team_b, src)
        self.status_bar.showMessage(f"Match #{self.active_match_id} started: {team_a} vs {team_b}")

    def _on_match_finished(self) -> None:
        if self.active_match_id is not None:
            pa, pb = self.pipeline.fsm.get_possession_split()
            dur = float(self.dashboard_tab.match_time_seconds)
            self.db.finish_match(self.active_match_id, self.live_score_a, self.live_score_b, dur, pa, pb)
            mid = self.active_match_id
            self.active_match_id = None
            self.status_bar.showMessage(f"Match #{mid} finished ({self.live_score_a} - {self.live_score_b})")
            self.summary_tab.reload_matches()
            self.summary_tab.display_match(mid)
            self.players_tab.reload_leaderboard()

    # -------------------------------------------------------------
    # Configuration and Tuning Slots
    # -------------------------------------------------------------
    def _on_calibration_saved(self, points: list) -> None:
        self.cfg.set("calibration_points", points)
        self.cfg.save()
        self.pipeline.update_from_config(self.cfg.data)

    def _on_live_calibration_updated(self, points: list) -> None:
        if len(points) == 4:
            self.pipeline.homography.set_points(points)

    def _on_hsv_bounds_changed(self, bounds: dict) -> None:
        self.pipeline.detector.set_hsv_bounds(bounds)

    def _on_contour_filters_changed(self, min_a: float, max_a: float, min_c: float) -> None:
        self.pipeline.detector.set_filters(min_a, max_a, min_c)

    def _on_hsv_saved(self) -> None:
        bounds = self.hsv_tab.get_hsv_bounds()
        self.cfg.set("hsv_bounds", bounds)
        self.cfg.set("contour_filter", {
            "min_area": float(self.hsv_tab.s_area_min.value()),
            "max_area": float(self.hsv_tab.s_area_max.value()),
            "min_circularity": float(self.hsv_tab.s_circ_min.value()) / 100.0,
            "morph_kernel_size": 3
        })
        self.cfg.save()

    def _on_distortion_changed(self, k1: float, k2: float, enabled: bool, focal: float) -> None:
        self.pipeline.fisheye.update_params(k1=k1, k2=k2, enabled=enabled, focal_scale=focal)

    def _on_distortion_saved(self) -> None:
        self.cfg.set("fisheye", {
            "enabled": self.fisheye_tab.chk_enable.isChecked(),
            "k1": self.fisheye_tab.s_k1.value() / 100.0,
            "k2": self.fisheye_tab.s_k2.value() / 100.0,
            "focal_scale": self.fisheye_tab.s_focal.value() / 100.0
        })
        self.cfg.save()

    def _apply_preset_key(self, preset_key: str) -> None:
        if self.cfg.apply_preset(preset_key):
            self.pipeline.update_from_config(self.cfg.data)
            vpath = self.cfg.get("video_path", "")
            self.worker.set_source(source_path=vpath, is_file=True)
            self.calibration_tab.set_initial_points(self.cfg.get("calibration_points", []))
            self.hsv_tab.set_hsv_bounds(self.cfg.get("hsv_bounds", {}))
            fe_cfg = self.cfg.get("fisheye", {})
            self.fisheye_tab.chk_enable.setChecked(bool(fe_cfg.get("enabled", False)))
            self.fisheye_tab.s_k1.setValue(int(float(fe_cfg.get("k1", -0.22)) * 100))
            self.fisheye_tab.s_k2.setValue(int(float(fe_cfg.get("k2", 0.05)) * 100))
            QMessageBox.information(self, "Preset Loaded", f"Applied preset: '{preset_key}'")

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video Recording", "", "Video Files (*.MOV *.mov *.mp4 *.avi *.mkv)"
        )
        if path:
            self.cfg.set("video_path", path)
            self.cfg.set("source_type", "file")
            self.cfg.save()
            self.worker.set_source(source_path=path, is_file=True)
            self.status_bar.showMessage(f"Loaded: {os.path.basename(path)}")

    def _select_webcam_dialog(self) -> None:
        idx, ok = QInputDialog.getInt(self, "Connect Webcam", "Enter UVC Camera Device Index (0, 1, 2...):", 0, 0, 10, 1)
        if ok:
            self.cfg.set("camera_index", idx)
            self.cfg.set("source_type", "webcam")
            self.cfg.save()
            self.worker.set_source(camera_index=idx, is_file=False)
            self.status_bar.showMessage(f"Connected to Webcam index #{idx}")

    def _show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "Foosball Tracking & Player Analytics",
            "<b>Foosball Tracking & Player Analytics v1.0</b><br><br>"
            "An advanced real-time computer vision system built for tournament-grade "
            "foosball match tracking, 4-point homography table rectification, optical fisheye unwarping, "
            "Kalman filter occlusion prediction, and discrete event analytics (Goals, Passes, Shots, Possession)."
        )

    def closeEvent(self, event) -> None:
        if self.active_match_id is not None:
            self._on_match_finished()
        self.worker.stop()
        self.db.close()
        event.accept()
