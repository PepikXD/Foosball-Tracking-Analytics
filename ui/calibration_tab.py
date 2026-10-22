"""
Interactive 4-Point Homography Perspective Calibration Tab.
Enables user to click 4 playfield corners directly on raw camera frames
and immediately previews the rectified 1200x700 top-down table view.
"""

from typing import List, Tuple, Optional
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QGroupBox
)


class ClickableImageLabel(QLabel):
    """Custom QLabel recording click positions mapped to original image resolution."""
    clicked_point = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.orig_image: Optional[QImage] = None
        self.calibration_points: List[Tuple[int, int]] = []

    def set_frame(self, q_img: QImage) -> None:
        self.orig_image = q_img
        self.update_pixmap()

    def set_points(self, points: List[List[float]]) -> None:
        self.calibration_points = [(int(p[0]), int(p[1])) for p in points]
        self.update_pixmap()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.orig_image is None or self.orig_image.isNull():
            return

        pos = event.position()
        lbl_w = self.width()
        lbl_h = self.height()
        img_w = self.orig_image.width()
        img_h = self.orig_image.height()

        # Compute scaling and offset caused by KeepAspectRatio
        scale = min(lbl_w / img_w, lbl_h / img_h)
        scaled_w = img_w * scale
        scaled_h = img_h * scale
        offset_x = (lbl_w - scaled_w) / 2.0
        offset_y = (lbl_h - scaled_h) / 2.0

        click_x = pos.x() - offset_x
        click_y = pos.y() - offset_y

        if 0 <= click_x <= scaled_w and 0 <= click_y <= scaled_h:
            orig_x = int(click_x / scale)
            orig_y = int(click_y / scale)
            self.clicked_point.emit(orig_x, orig_y)

    def update_pixmap(self) -> None:
        if self.orig_image is None or self.orig_image.isNull():
            return

        pix = QPixmap.fromImage(self.orig_image)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw existing corners and polygon
        pts = self.calibration_points
        if len(pts) > 1:
            pen = QPen(QColor(0, 255, 255), 3)
            painter.setPen(pen)
            for i in range(len(pts) - 1):
                painter.drawLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
            if len(pts) == 4:
                painter.drawLine(pts[3][0], pts[3][1], pts[0][0], pts[0][1])

        labels = ["1. TL", "2. TR", "3. BR", "4. BL"]
        for i, pt in enumerate(pts):
            painter.setBrush(QColor(239, 68, 68))
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawEllipse(QPoint(pt[0], pt[1]), 8, 8)
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            painter.setPen(QColor(255, 255, 0))
            lbl = labels[i] if i < len(labels) else str(i + 1)
            painter.drawText(pt[0] + 12, pt[1] - 8, lbl)

        painter.end()

        scaled = pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_pixmap()


class CalibrationTab(QWidget):
    """Perspective Calibration tab with interactive 4-point corner selection."""

    calibration_saved = pyqtSignal(list)  # 4 points [[x, y], ...]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_points: List[Tuple[int, int]] = []
        self._latest_raw_qimg: Optional[QImage] = None
        self._latest_rect_qimg: Optional[QImage] = None

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header instructions
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 6px;")
        h_layout = QHBoxLayout(header_frame)

        self.lbl_instruction = QLabel("Click 4 table playfield corners clockwise: 1. Top-Left -> 2. Top-Right -> 3. Bottom-Right -> 4. Bottom-Left")
        self.lbl_instruction.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        h_layout.addWidget(self.lbl_instruction)
        h_layout.addStretch()

        self.btn_reset = QPushButton("Reset Points")
        self.btn_reset.setStyleSheet("background-color: #475569; color: white; padding: 4px 12px; border-radius: 4px;")
        self.btn_reset.clicked.connect(self._reset_points)

        self.btn_preset_phone = QPushButton("Phone Cam Preset")
        self.btn_preset_phone.setStyleSheet("background-color: #0369a1; color: white; padding: 4px 12px; border-radius: 4px;")
        self.btn_preset_phone.clicked.connect(self._apply_phone_preset)

        self.btn_preset_action = QPushButton("Action Cam Preset")
        self.btn_preset_action.setStyleSheet("background-color: #0369a1; color: white; padding: 4px 12px; border-radius: 4px;")
        self.btn_preset_action.clicked.connect(self._apply_action_preset)

        self.btn_save = QPushButton("Apply & Save Calibration")
        self.btn_save.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 4px 16px; border-radius: 4px;")
        self.btn_save.clicked.connect(self._save_calibration)

        h_layout.addWidget(self.btn_reset)
        h_layout.addWidget(self.btn_preset_phone)
        h_layout.addWidget(self.btn_preset_action)
        h_layout.addWidget(self.btn_save)
        layout.addWidget(header_frame)

        # Display Splitter: Raw Camera Canvas (left) and Rectified Preview (right)
        preview_layout = QHBoxLayout()

        # Raw Canvas Box
        raw_box = QGroupBox("Camera Frame (Click 4 Corners)")
        raw_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        raw_layout = QVBoxLayout(raw_box)
        self.canvas_label = ClickableImageLabel()
        self.canvas_label.setMinimumSize(540, 360)
        self.canvas_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_label.setStyleSheet("background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px;")
        self.canvas_label.clicked_point.connect(self._on_corner_clicked)
        raw_layout.addWidget(self.canvas_label)
        preview_layout.addWidget(raw_box, stretch=3)

        # Rectified Preview Box
        rect_box = QGroupBox("Rectified 1200x700 Top-Down Preview")
        rect_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        rect_layout = QVBoxLayout(rect_box)
        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(360, 240)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px;")
        rect_layout.addWidget(self.preview_label)
        preview_layout.addWidget(rect_box, stretch=2)

        layout.addLayout(preview_layout, stretch=1)

    def set_initial_points(self, points: List[List[float]]) -> None:
        self.current_points = [(int(p[0]), int(p[1])) for p in points]
        self.canvas_label.set_points(points)

    def update_frames(self, q_rect: QImage, q_raw: QImage) -> None:
        self._latest_raw_qimg = q_raw
        self._latest_rect_qimg = q_rect

        self.canvas_label.set_frame(q_raw)

        if not q_rect.isNull():
            pix = QPixmap.fromImage(q_rect)
            scaled = pix.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
            self.preview_label.setPixmap(scaled)

    def _on_corner_clicked(self, x: int, y: int) -> None:
        if len(self.current_points) >= 4:
            self.current_points.clear()

        self.current_points.append((x, y))
        self.canvas_label.calibration_points = list(self.current_points)
        self.canvas_label.update_pixmap()

        step = len(self.current_points)
        if step == 1:
            self.lbl_instruction.setText("Point 1 (Top-Left) set. Click Point 2: Top-Right")
        elif step == 2:
            self.lbl_instruction.setText("Point 2 (Top-Right) set. Click Point 3: Bottom-Right")
        elif step == 3:
            self.lbl_instruction.setText("Point 3 (Bottom-Right) set. Click Point 4: Bottom-Left")
        elif step == 4:
            self.lbl_instruction.setText("All 4 corners set! Click 'Apply & Save Calibration' to activate.")

    def _reset_points(self) -> None:
        self.current_points.clear()
        self.canvas_label.calibration_points.clear()
        self.canvas_label.update_pixmap()
        self.lbl_instruction.setText("Click 4 table playfield corners clockwise: 1. Top-Left -> 2. Top-Right -> 3. Bottom-Right -> 4. Bottom-Left")

    def _apply_phone_preset(self) -> None:
        pts = [[720, 135], [1730, 15], [1895, 785], [870, 650]]
        self.set_initial_points(pts)
        self._save_calibration()

    def _apply_action_preset(self) -> None:
        pts = [[675, 205], [1560, 85], [1690, 720], [805, 845]]
        self.set_initial_points(pts)
        self._save_calibration()

    def _save_calibration(self) -> None:
        if len(self.current_points) != 4:
            QMessageBox.warning(self, "Incomplete", "Please click all 4 table corners before saving.")
            return

        pts_list = [[p[0], p[1]] for p in self.current_points]
        self.calibration_saved.emit(pts_list)
        QMessageBox.information(self, "Calibrated", "Perspective calibration successfully applied and saved!")
