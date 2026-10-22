"""
Interactive Drag-and-Drop Homography Perspective Calibration Tab.
Allows user to drag and drop the 4 corner calibration points directly on the camera frame
with instantaneous live re-warping preview on the right vertical view.
"""

from typing import List, Tuple, Optional
import numpy as np
import cv2
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QGroupBox, QSplitter
)

from core.homography import HomographyTransformer
from ui.video_worker import cv_mat_to_qimage


class DraggableCornerCanvas(QLabel):
    """
    Interactive canvas displaying the camera frame where the 4 corner calibration
    points can be clicked and dragged in real-time.
    """
    corner_dragged = pyqtSignal(list)   # [[x, y], ...] on every mouse move while dragging
    points_committed = pyqtSignal(list) # [[x, y], ...] on mouse release or complete set

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.orig_image: Optional[QImage] = None
        self.raw_frame_mat: Optional[np.ndarray] = None
        self.calibration_points: List[Tuple[float, float]] = []
        self.active_corner_idx: Optional[int] = None
        self.hover_corner_idx: Optional[int] = None

        # Grab radius in image coordinate pixels
        self.grab_radius_px = 35.0

    def set_frame(self, q_img: QImage, raw_mat: Optional[np.ndarray] = None) -> None:
        self.orig_image = q_img
        if raw_mat is not None:
            self.raw_frame_mat = raw_mat
        self.update_pixmap()

    def set_points(self, points: List[List[float]]) -> None:
        self.calibration_points = [(float(p[0]), float(p[1])) for p in points]
        self.update_pixmap()

    def _widget_to_image_coords(self, pos) -> Optional[Tuple[float, float]]:
        """Converts widget pixel position to original image coordinate."""
        if self.orig_image is None or self.orig_image.isNull():
            return None

        lbl_w = self.width()
        lbl_h = self.height()
        img_w = self.orig_image.width()
        img_h = self.orig_image.height()

        scale = min(lbl_w / img_w, lbl_h / img_h)
        scaled_w = img_w * scale
        scaled_h = img_h * scale
        offset_x = (lbl_w - scaled_w) / 2.0
        offset_y = (lbl_h - scaled_h) / 2.0

        click_x = pos.x() - offset_x
        click_y = pos.y() - offset_y

        if 0 <= click_x <= scaled_w and 0 <= click_y <= scaled_h:
            orig_x = max(0.0, min(float(img_w), click_x / scale))
            orig_y = max(0.0, min(float(img_h), click_y / scale))
            return orig_x, orig_y
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return

        coords = self._widget_to_image_coords(event.position())
        if coords is None:
            return

        cx, cy = coords

        # Check if clicking existing corner to drag
        clicked_idx = None
        min_dist = float("inf")
        for i, pt in enumerate(self.calibration_points):
            dist = np.hypot(pt[0] - cx, pt[1] - cy)
            if dist < self.grab_radius_px and dist < min_dist:
                min_dist = dist
                clicked_idx = i

        if clicked_idx is not None:
            self.active_corner_idx = clicked_idx
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif len(self.calibration_points) < 4:
            # Add new corner point if fewer than 4 exist
            self.calibration_points.append((cx, cy))
            self.update_pixmap()
            if len(self.calibration_points) == 4:
                pts_list = [[p[0], p[1]] for p in self.calibration_points]
                self.points_committed.emit(pts_list)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        coords = self._widget_to_image_coords(event.position())

        # If dragging an active corner
        if self.active_corner_idx is not None and coords is not None:
            cx, cy = coords
            self.calibration_points[self.active_corner_idx] = (cx, cy)
            self.update_pixmap()

            # Emit live drag signal for instant re-warp
            pts_list = [[p[0], p[1]] for p in self.calibration_points]
            self.corner_dragged.emit(pts_list)
            return

        # Otherwise handle hover cursor feedback
        if coords is not None and len(self.calibration_points) > 0:
            cx, cy = coords
            hovered = None
            for i, pt in enumerate(self.calibration_points):
                if np.hypot(pt[0] - cx, pt[1] - cy) < self.grab_radius_px:
                    hovered = i
                    break

            if hovered != self.hover_corner_idx:
                self.hover_corner_idx = hovered
                if hovered is not None:
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.CrossCursor)
                self.update_pixmap()
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.active_corner_idx is not None:
            self.active_corner_idx = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.hover_corner_idx is not None else Qt.CursorShape.ArrowCursor)
            if len(self.calibration_points) == 4:
                pts_list = [[p[0], p[1]] for p in self.calibration_points]
                self.points_committed.emit(pts_list)

    def update_pixmap(self) -> None:
        if self.orig_image is None or self.orig_image.isNull():
            return

        pix = QPixmap.fromImage(self.orig_image)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pts = self.calibration_points

        # Draw connecting polygon
        if len(pts) > 1:
            pen = QPen(QColor(56, 189, 248), 3)
            painter.setPen(pen)
            for i in range(len(pts) - 1):
                painter.drawLine(int(pts[i][0]), int(pts[i][1]), int(pts[i + 1][0]), int(pts[i + 1][1]))
            if len(pts) == 4:
                painter.drawLine(int(pts[3][0]), int(pts[3][1]), int(pts[0][0]), int(pts[0][1]))

        # Draw draggable corner handles
        labels = ["1: TL (0,0)", "2: TR (700,0)", "3: BR (700,1200)", "4: BL (0,1200)"]
        colors = [
            QColor(56, 189, 248),   # Cyan for TL
            QColor(74, 222, 128),   # Green for TR
            QColor(248, 113, 113),  # Red for BR
            QColor(250, 204, 21),   # Yellow for BL
        ]

        for i, pt in enumerate(pts):
            px, py = int(pt[0]), int(pt[1])
            is_active = (i == self.active_corner_idx)
            is_hover = (i == self.hover_corner_idx)
            base_col = colors[i % len(colors)]

            # Outer ring glow
            glow_rad = 18 if (is_active or is_hover) else 14
            glow_col = QColor(base_col)
            glow_col.setAlpha(120 if (is_active or is_hover) else 60)
            painter.setBrush(glow_col)
            painter.setPen(QPen(base_col, 2 if not is_active else 3))
            painter.drawEllipse(QPointF(px, py), glow_rad, glow_rad)

            # Center core dot
            painter.setBrush(QColor(255, 255, 255))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(px, py), 4, 4)

            # Label badge
            lbl = labels[i] if i < len(labels) else f"Corner {i + 1}"
            coord_str = f"({px},{py})"
            painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))

            # Text background badge
            text_full = f"{lbl} {coord_str}"
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(text_full)
            th = fm.height()

            painter.setBrush(QColor(15, 23, 42, 210))
            painter.setPen(QPen(base_col, 1))
            painter.drawRoundedRect(px + 12, py - th - 4, tw + 10, th + 4, 4, 4)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(px + 17, py - 6, text_full)

        painter.end()

        scaled = pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_pixmap()


class CalibrationTab(QWidget):
    """
    Perspective Calibration Tab.
    Provides drag-and-drop corner adjustment on the raw camera view with instant live preview
    of the vertical (700x1200) rectified table.
    """
    calibration_saved = pyqtSignal(list)       # [[x, y], ...] saved to config
    live_calibration_updated = pyqtSignal(list) # [[x, y], ...] emitted live during drag

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_points: List[Tuple[float, float]] = []
        self._latest_raw_qimg: Optional[QImage] = None
        self._latest_raw_mat: Optional[np.ndarray] = None

        # Dedicated homography instance for instantaneous warp feedback
        self.live_homography = HomographyTransformer(target_width=700, target_height=1200)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header bar with instructions and action buttons
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 6px;")
        h_layout = QHBoxLayout(header_frame)

        self.lbl_instruction = QLabel("Drag & drop any of the 4 corner handles. The rectified vertical table will update instantly.")
        self.lbl_instruction.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
        h_layout.addWidget(self.lbl_instruction)
        h_layout.addStretch()

        self.btn_reset = QPushButton("Reset Points")
        self.btn_reset.setStyleSheet("background-color: #475569; color: white; padding: 4px 12px; border-radius: 4px;")
        self.btn_reset.clicked.connect(self._reset_points)

        self.btn_preset_phone = QPushButton("Phone Cam (Vertical)")
        self.btn_preset_phone.setStyleSheet("background-color: #0369a1; color: white; padding: 4px 12px; border-radius: 4px;")
        self.btn_preset_phone.clicked.connect(self._apply_phone_preset)

        self.btn_preset_action = QPushButton("Action Cam (Vertical)")
        self.btn_preset_action.setStyleSheet("background-color: #0369a1; color: white; padding: 4px 12px; border-radius: 4px;")
        self.btn_preset_action.clicked.connect(self._apply_action_preset)

        self.btn_save = QPushButton("Save Calibration to Config")
        self.btn_save.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 4px 16px; border-radius: 4px;")
        self.btn_save.clicked.connect(self._save_calibration)

        h_layout.addWidget(self.btn_reset)
        h_layout.addWidget(self.btn_preset_phone)
        h_layout.addWidget(self.btn_preset_action)
        h_layout.addWidget(self.btn_save)
        layout.addWidget(header_frame)

        # Main Splitter: Draggable Left View (Raw Camera) & Instant Right View (Vertical Rectified)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Group: Draggable Camera Frame
        left_box = QGroupBox("Camera Frame (Drag & Drop Corners 1..4)")
        left_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        left_layout = QVBoxLayout(left_box)

        self.canvas_label = DraggableCornerCanvas()
        self.canvas_label.setMinimumSize(520, 400)
        self.canvas_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas_label.setStyleSheet("background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px;")
        self.canvas_label.corner_dragged.connect(self._on_live_corner_dragged)
        self.canvas_label.points_committed.connect(self._on_points_committed)
        left_layout.addWidget(self.canvas_label)

        splitter.addWidget(left_box)

        # Right Group: Calibrated Vertical View (700x1200)
        right_box = QGroupBox("Calibrated Vertical Table (700x1200 Live Rectification)")
        right_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        right_layout = QVBoxLayout(right_box)

        self.preview_label = QLabel()
        self.preview_label.setMinimumSize(320, 500)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px;")
        right_layout.addWidget(self.preview_label)

        splitter.addWidget(right_box)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter, stretch=1)

    def set_initial_points(self, points: List[List[float]]) -> None:
        self.current_points = [(float(p[0]), float(p[1])) for p in points]
        self.canvas_label.set_points(points)
        if len(points) == 4:
            self.live_homography.set_points(points)

    def update_frames(self, q_rect: QImage, q_raw: QImage) -> None:
        self._latest_raw_qimg = q_raw

        # If not actively dragging, update camera canvas with newest frame
        if self.canvas_label.active_corner_idx is None:
            self.canvas_label.set_frame(q_raw)

            # Update right preview with rectified frame
            if not q_rect.isNull():
                pix = QPixmap.fromImage(q_rect)
                scaled = pix.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
                self.preview_label.setPixmap(scaled)

    def _on_live_corner_dragged(self, points: List[List[float]]) -> None:
        """Called instantaneously on every mouse move while dragging a corner handle."""
        self.current_points = [(float(p[0]), float(p[1])) for p in points]
        if len(points) == 4:
            self.live_homography.set_points(points)

            # Immediately update right view if raw image exists
            if self._latest_raw_qimg is not None and not self._latest_raw_qimg.isNull():
                # Convert QImage to numpy BGR
                w = self._latest_raw_qimg.width()
                h = self._latest_raw_qimg.height()
                ptr = self._latest_raw_qimg.bits()
                ptr.setsize(h * self._latest_raw_qimg.bytesPerLine())
                arr = np.array(ptr).reshape((h, self._latest_raw_qimg.bytesPerLine() // 3, 3))
                bgr = cv2.cvtColor(arr[:, :w], cv2.COLOR_RGB2BGR)

                # Live warp to vertical 700x1200
                warped = self.live_homography.warp(bgr)
                if warped is not None:
                    # Draw subtle goal lines
                    cv2.rectangle(warped, (210, 0), (490, 65), (0, 0, 180), 2)
                    cv2.rectangle(warped, (210, 1135), (490, 1200), (0, 0, 180), 2)

                    q_warped = cv_mat_to_qimage(warped)
                    pix = QPixmap.fromImage(q_warped)
                    scaled = pix.scaled(self.preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
                    self.preview_label.setPixmap(scaled)

            # Also notify pipeline to update live in memory
            self.live_calibration_updated.emit(points)

    def _on_points_committed(self, points: List[List[float]]) -> None:
        self.current_points = [(float(p[0]), float(p[1])) for p in points]
        self.calibration_saved.emit(points)

    def _reset_points(self) -> None:
        self.current_points.clear()
        self.canvas_label.calibration_points.clear()
        self.canvas_label.update_pixmap()
        self.lbl_instruction.setText("Click 4 table playfield corners clockwise: 1. Top-Left -> 2. Top-Right -> 3. Bottom-Right -> 4. Bottom-Left")

    def _apply_phone_preset(self) -> None:
        pts = [[870, 650], [720, 135], [1730, 15], [1895, 785]]
        self.set_initial_points(pts)
        self.calibration_saved.emit(pts)

    def _apply_action_preset(self) -> None:
        pts = [[805, 845], [675, 205], [1560, 85], [1690, 720]]
        self.set_initial_points(pts)
        self.calibration_saved.emit(pts)

    def _save_calibration(self) -> None:
        if len(self.current_points) != 4:
            QMessageBox.warning(self, "Incomplete", "Please set all 4 table corners before saving.")
            return

        pts_list = [[p[0], p[1]] for p in self.current_points]
        self.calibration_saved.emit(pts_list)
        QMessageBox.information(self, "Saved", "Vertical table calibration successfully saved to config!")
