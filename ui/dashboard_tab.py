"""
Main Live Match Dashboard Tab.
Presents the live scoreboard, match timer, vertical 700x1200 table view,
ball speed telemetry, active rod possession indicators, and real-time event ticker.
"""

from typing import Optional, Dict, Any
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QGroupBox
)

from core.fsm import GameEvent, EventType


class DashboardTab(QWidget):
    """Main live match analytics dashboard optimized for vertical table presentation."""

    # UI interaction signals
    pause_toggled = pyqtSignal()
    seek_requested = pyqtSignal(float)
    speed_changed = pyqtSignal(float)
    score_override = pyqtSignal(str, int)  # team ('A' or 'B'), delta (+1 or -1)
    match_started = pyqtSignal(str, str)   # team_a_name, team_b_name
    match_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.score_a = 0
        self.score_b = 0
        self.match_time_seconds = 0
        self.match_running = False

        self._match_timer = QTimer(self)
        self._match_timer.setInterval(1000)
        self._match_timer.timeout.connect(self._on_clock_tick)

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ---------------------------------------------------------
        # 1. Top Bar: Match Controls, Clock, and Scoreboard
        # ---------------------------------------------------------
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setStyleSheet("""
            #topBar {
                background-color: #1e293b;
                border-radius: 8px;
                padding: 6px;
            }
        """)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 6, 12, 6)

        # Team A Box (Blue / Top Goal)
        team_a_box = QHBoxLayout()
        self.btn_sub_a = QPushButton("-")
        self.btn_sub_a.setFixedSize(28, 28)
        self.btn_sub_a.setStyleSheet("background-color: #334155; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_sub_a.clicked.connect(lambda: self.score_override.emit("A", -1))

        self.lbl_team_a = QLabel("TEAM BLUE (TOP)")
        self.lbl_team_a.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 15px;")

        self.lbl_score_a = QLabel("0")
        self.lbl_score_a.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 34px; padding: 0 10px;")

        self.btn_add_a = QPushButton("+")
        self.btn_add_a.setFixedSize(28, 28)
        self.btn_add_a.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_add_a.clicked.connect(lambda: self.score_override.emit("A", 1))

        team_a_box.addWidget(self.btn_sub_a)
        team_a_box.addWidget(self.lbl_team_a)
        team_a_box.addSpacing(8)
        team_a_box.addWidget(self.lbl_score_a)
        team_a_box.addWidget(self.btn_add_a)

        # Match Clock / State
        center_box = QVBoxLayout()
        self.lbl_clock = QLabel("00:00")
        self.lbl_clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_clock.setStyleSheet("color: #f8fafc; font-size: 22px; font-weight: bold; font-family: monospace;")

        clock_ctrls = QHBoxLayout()
        self.btn_start_match = QPushButton("Start Match")
        self.btn_start_match.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 4px 12px; border-radius: 4px;")
        self.btn_start_match.clicked.connect(self._toggle_match_state)

        self.btn_finish_match = QPushButton("End Match")
        self.btn_finish_match.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; padding: 4px 12px; border-radius: 4px;")
        self.btn_finish_match.clicked.connect(self._finish_match_clicked)

        clock_ctrls.addWidget(self.btn_start_match)
        clock_ctrls.addWidget(self.btn_finish_match)

        center_box.addWidget(self.lbl_clock)
        center_box.addLayout(clock_ctrls)

        # Team B Box (Red / Bottom Goal)
        team_b_box = QHBoxLayout()
        self.btn_sub_b = QPushButton("-")
        self.btn_sub_b.setFixedSize(28, 28)
        self.btn_sub_b.setStyleSheet("background-color: #334155; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_sub_b.clicked.connect(lambda: self.score_override.emit("B", -1))

        self.lbl_score_b = QLabel("0")
        self.lbl_score_b.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 34px; padding: 0 10px;")

        self.lbl_team_b = QLabel("TEAM RED (BOTTOM)")
        self.lbl_team_b.setStyleSheet("color: #f87171; font-weight: bold; font-size: 15px;")

        self.btn_add_b = QPushButton("+")
        self.btn_add_b.setFixedSize(28, 28)
        self.btn_add_b.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_add_b.clicked.connect(lambda: self.score_override.emit("B", 1))

        team_b_box.addWidget(self.btn_sub_b)
        team_b_box.addWidget(self.lbl_score_b)
        team_b_box.addSpacing(8)
        team_b_box.addWidget(self.lbl_team_b)
        team_b_box.addWidget(self.btn_add_b)

        top_layout.addLayout(team_a_box)
        top_layout.addStretch()
        top_layout.addLayout(center_box)
        top_layout.addStretch()
        top_layout.addLayout(team_b_box)

        main_layout.addWidget(top_bar)

        # ---------------------------------------------------------
        # 2. Main Middle Area: Splitter (Vertical Video Viewport & Telemetry/Events)
        # ---------------------------------------------------------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Center / Left: Vertical Video Display
        video_container = QWidget()
        vid_layout = QVBoxLayout(video_container)
        vid_layout.setContentsMargins(0, 0, 0, 0)
        vid_layout.setSpacing(6)

        # View Toggle Bar
        view_toggle_layout = QHBoxLayout()
        self.lbl_view_title = QLabel("Vertical Rectified View (700x1200)")
        self.lbl_view_title.setStyleSheet("color: #94a3b8; font-weight: bold;")
        self.combo_view_mode = QComboBox()
        self.combo_view_mode.addItems(["Rectified Table (Vertical 700x1200)", "Raw Camera Frame", "HSV Detection Mask"])
        self.combo_view_mode.setStyleSheet("background-color: #334155; color: white; padding: 3px 8px; border-radius: 4px;")
        self.combo_view_mode.currentIndexChanged.connect(self._on_view_mode_changed)

        self.lbl_fps = QLabel("FPS: --")
        self.lbl_fps.setStyleSheet("color: #10b981; font-weight: bold;")

        view_toggle_layout.addWidget(self.lbl_view_title)
        view_toggle_layout.addStretch()
        view_toggle_layout.addWidget(self.lbl_fps)
        view_toggle_layout.addSpacing(10)
        view_toggle_layout.addWidget(self.combo_view_mode)
        vid_layout.addLayout(view_toggle_layout)

        # Vertical Video Frame Display (Portrait Aspect Ratio)
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: #0b0f19; border: 1px solid #334155; border-radius: 6px;")
        self.video_label.setMinimumSize(420, 600)
        vid_layout.addWidget(self.video_label, stretch=1)

        # Video Playback Controls Bar
        playback_bar = QHBoxLayout()
        self.btn_play_pause = QPushButton("Pause")
        self.btn_play_pause.setStyleSheet("background-color: #334155; color: white; font-weight: bold; padding: 4px 12px; border-radius: 4px;")
        self.btn_play_pause.clicked.connect(lambda: self.pause_toggled.emit())

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.sliderMoved.connect(lambda v: self.seek_requested.emit(v / 1000.0))

        self.lbl_time_pos = QLabel("00:00 / 00:00")
        self.lbl_time_pos.setStyleSheet("color: #94a3b8; font-size: 11px; font-family: monospace;")

        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.5x", "1.0x", "1.5x", "2.0x"])
        self.combo_speed.setCurrentIndex(1)
        self.combo_speed.setStyleSheet("background-color: #334155; color: white; border-radius: 4px;")
        self.combo_speed.currentTextChanged.connect(self._on_speed_selected)

        playback_bar.addWidget(self.btn_play_pause)
        playback_bar.addWidget(self.seek_slider)
        playback_bar.addWidget(self.lbl_time_pos)
        playback_bar.addWidget(self.combo_speed)
        vid_layout.addLayout(playback_bar)

        splitter.addWidget(video_container)

        # Right Column: Live HUD Telemetry Cards & Live Event Ticker
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # HUD Telemetry Frame
        hud_frame = QFrame()
        hud_frame.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 8px;")
        hud_vlayout = QVBoxLayout(hud_frame)
        hud_vlayout.setSpacing(6)

        # Speed Row
        r_speed = QHBoxLayout()
        r_speed.addWidget(QLabel("Live Ball Speed:"))
        self.lbl_speed_val = QLabel("0.0 km/h")
        self.lbl_speed_val.setStyleSheet("color: #facc15; font-size: 20px; font-weight: bold;")
        r_speed.addWidget(self.lbl_speed_val)
        r_speed.addStretch()

        self.lbl_tracking_status = QLabel("SEARCHING")
        self.lbl_tracking_status.setStyleSheet("background-color: #475569; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;")
        r_speed.addWidget(self.lbl_tracking_status)
        hud_vlayout.addLayout(r_speed)

        # Active Rod Row
        r_rod = QHBoxLayout()
        r_rod.addWidget(QLabel("Active Rod:"))
        self.lbl_active_rod = QLabel("Midfield")
        self.lbl_active_rod.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 14px;")
        r_rod.addWidget(self.lbl_active_rod)
        r_rod.addStretch()
        hud_vlayout.addLayout(r_rod)

        # Possession Split Row
        r_poss = QHBoxLayout()
        r_poss.addWidget(QLabel("Possession:"))
        self.lbl_poss_split = QLabel("50.0% Blue | 50.0% Red")
        self.lbl_poss_split.setStyleSheet("color: #e2e8f0; font-weight: bold;")
        r_poss.addWidget(self.lbl_poss_split)
        r_poss.addStretch()
        hud_vlayout.addLayout(r_poss)

        right_layout.addWidget(hud_frame)

        # Live Event Log Panel
        event_panel = QFrame()
        event_panel.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 8px;")
        event_layout = QVBoxLayout(event_panel)
        event_layout.setContentsMargins(6, 6, 6, 6)

        event_header = QLabel("LIVE MATCH EVENT TICKER")
        event_header.setStyleSheet("color: #94a3b8; font-weight: bold; font-size: 12px;")
        event_layout.addWidget(event_header)

        self.event_table = QTableWidget(0, 3)
        self.event_table.setHorizontalHeaderLabels(["Time", "Event", "Details"])
        self.event_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.event_table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 4px;
                gridline-color: #1e293b;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                font-weight: bold;
                border: none;
                padding: 4px;
            }
        """)
        event_layout.addWidget(self.event_table)
        right_layout.addWidget(event_panel, stretch=1)

        splitter.addWidget(right_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter, stretch=1)

    # -------------------------------------------------------------
    # Slot handlers
    # -------------------------------------------------------------
    def _toggle_match_state(self) -> None:
        if not self.match_running:
            self.match_running = True
            self.match_time_seconds = 0
            self._match_timer.start()
            self.btn_start_match.setText("Pause Match")
            self.btn_start_match.setStyleSheet("background-color: #eab308; color: black; font-weight: bold; padding: 4px 12px; border-radius: 4px;")
            self.match_started.emit(self.lbl_team_a.text(), self.lbl_team_b.text())
        else:
            self.match_running = False
            self._match_timer.stop()
            self.btn_start_match.setText("Resume Match")
            self.btn_start_match.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 4px 12px; border-radius: 4px;")

    def _finish_match_clicked(self) -> None:
        self.match_running = False
        self._match_timer.stop()
        self.btn_start_match.setText("Start Match")
        self.btn_start_match.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 4px 12px; border-radius: 4px;")
        self.match_finished.emit()

    def _on_clock_tick(self) -> None:
        self.match_time_seconds += 1
        m = self.match_time_seconds // 60
        s = self.match_time_seconds % 60
        self.lbl_clock.setText(f"{m:02d}:{s:02d}")

    def _on_speed_selected(self, text: str) -> None:
        try:
            val = float(text.replace("x", ""))
            self.speed_changed.emit(val)
        except ValueError:
            pass

    def _on_view_mode_changed(self, idx: int) -> None:
        titles = [
            "View: Vertical Rectified Table (700x1200)",
            "View: Raw Camera Frame",
            "View: HSV Detection Mask"
        ]
        if 0 <= idx < len(titles):
            self.lbl_view_title.setText(titles[idx])

    # -------------------------------------------------------------
    # Update from Worker Thread
    # -------------------------------------------------------------
    def update_frame(self, q_rect: QImage, q_raw: QImage, q_mask: QImage) -> None:
        """Displays active frame in vertical portrait viewport."""
        mode = self.combo_view_mode.currentIndex()
        target_img = q_rect if mode == 0 else (q_raw if mode == 1 else q_mask)

        if not target_img.isNull():
            pix = QPixmap.fromImage(target_img)
            scaled = pix.scaled(
                self.video_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            self.video_label.setPixmap(scaled)

    def update_telemetry(self, telemetry: Dict[str, Any]) -> None:
        """Updates speed, active rod, possession, and status badges."""
        speed = telemetry.get("speed_kmh", 0.0)
        self.lbl_speed_val.setText(f"{speed:.1f} km/h")
        if speed > 18.0:
            self.lbl_speed_val.setStyleSheet("color: #ef4444; font-size: 20px; font-weight: bold;")
        elif speed > 10.0:
            self.lbl_speed_val.setStyleSheet("color: #facc15; font-size: 20px; font-weight: bold;")
        else:
            self.lbl_speed_val.setStyleSheet("color: #38bdf8; font-size: 20px; font-weight: bold;")

        rod = telemetry.get("current_rod")
        self.lbl_active_rod.setText(str(rod) if rod else "Midfield")

        pa = telemetry.get("possession_a", 50.0)
        pb = telemetry.get("possession_b", 50.0)
        self.lbl_poss_split.setText(f"{pa:.1f}% Blue | {pb:.1f}% Red")

        fps = telemetry.get("fps", 0.0)
        self.lbl_fps.setText(f"FPS: {fps:.1f}")

        is_trk = telemetry.get("is_tracking", False)
        is_occ = telemetry.get("is_occluded", False)
        if is_trk and not is_occ:
            self.lbl_tracking_status.setText("TRACKING")
            self.lbl_tracking_status.setStyleSheet("background-color: #16a34a; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;")
        elif is_trk and is_occ:
            occ_f = telemetry.get("occlusion_frames", 0)
            self.lbl_tracking_status.setText(f"OCCLUDED ({occ_f})")
            self.lbl_tracking_status.setStyleSheet("background-color: #eab308; color: black; padding: 2px 8px; border-radius: 4px; font-size: 11px;")
        else:
            self.lbl_tracking_status.setText("LOST")
            self.lbl_tracking_status.setStyleSheet("background-color: #dc2626; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;")

    def update_playback_state(self, is_playing: bool, current_sec: float, total_sec: float) -> None:
        self.btn_play_pause.setText("Pause" if is_playing else "Play")
        if total_sec > 0:
            pct = int((current_sec / total_sec) * 1000)
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(pct)
            self.seek_slider.blockSignals(False)

        cur_m = int(current_sec // 60)
        cur_s = int(current_sec % 60)
        tot_m = int(total_sec // 60)
        tot_s = int(total_sec % 60)
        self.lbl_time_pos.setText(f"{cur_m:02d}:{cur_s:02d} / {tot_m:02d}:{tot_s:02d}")

    def set_scores(self, a: int, b: int) -> None:
        self.score_a = a
        self.score_b = b
        self.lbl_score_a.setText(str(self.score_a))
        self.lbl_score_b.setText(str(self.score_b))

    def add_event(self, event: GameEvent) -> None:
        """Appends a new event entry into the live ticker table."""
        row = 0
        self.event_table.insertRow(row)

        sec = event.timestamp_ms / 1000.0
        m = int(sec // 60)
        s = int(sec % 60)
        time_item = QTableWidgetItem(f"{m:02d}:{s:02d}")
        type_item = QTableWidgetItem(event.event_type.value)
        desc_item = QTableWidgetItem(event.details)

        if event.event_type == EventType.GOAL:
            color = QColor("#ef4444") if event.team == "B" else QColor("#38bdf8")
            type_item.setForeground(color)
            type_item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        elif event.event_type == EventType.PASS_COMPLETE:
            type_item.setForeground(QColor("#10b981"))
        elif event.event_type == EventType.SHOT_ATTEMPT:
            type_item.setForeground(QColor("#f59e0b"))

        self.event_table.setItem(row, 0, time_item)
        self.event_table.setItem(row, 1, type_item)
        self.event_table.setItem(row, 2, desc_item)

        if self.event_table.rowCount() > 50:
            self.event_table.removeRow(50)
