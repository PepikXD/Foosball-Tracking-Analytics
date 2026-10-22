"""
HSV Color Threshold Tuning Utility Tab.
Provides real-time sliders and dual-range mask previews to tune color boundaries
under varying foosball ball materials (orange, yellow, white) and changing ambient lighting.
"""

from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QGroupBox, QFrame, QGridLayout, QMessageBox
)


class HSVTunerTab(QWidget):
    """Interactive HSV Color Threshold and Contour Filter Tuner."""

    hsv_bounds_changed = pyqtSignal(dict)
    contour_filters_changed = pyqtSignal(float, float, float)
    save_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Left Column: Sliders and Presets
        controls_panel = QFrame()
        controls_panel.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 10px;")
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setSpacing(8)

        # Presets Box
        preset_box = QGroupBox("Color Presets")
        preset_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        preset_layout = QHBoxLayout(preset_box)

        self.btn_preset_orange = QPushButton("Orange/Red (Test Videos)")
        self.btn_preset_orange.setStyleSheet("background-color: #ea580c; color: white; padding: 4px 8px; border-radius: 4px;")
        self.btn_preset_orange.clicked.connect(self._preset_orange)

        self.btn_preset_yellow = QPushButton("Yellow ITSF Ball")
        self.btn_preset_yellow.setStyleSheet("background-color: #ca8a04; color: white; padding: 4px 8px; border-radius: 4px;")
        self.btn_preset_yellow.clicked.connect(self._preset_yellow)

        self.btn_preset_white = QPushButton("White Ball")
        self.btn_preset_white.setStyleSheet("background-color: #475569; color: white; padding: 4px 8px; border-radius: 4px;")
        self.btn_preset_white.clicked.connect(self._preset_white)

        preset_layout.addWidget(self.btn_preset_orange)
        preset_layout.addWidget(self.btn_preset_yellow)
        preset_layout.addWidget(self.btn_preset_white)
        controls_layout.addWidget(preset_box)

        # Range 1 Sliders (Hue 1, Sat, Val)
        r1_box = QGroupBox("HSV Thresholds: Range 1 (Primary)")
        r1_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        r1_grid = QGridLayout(r1_box)

        # H1 Min / Max
        self.s_h1_min, self.lbl_h1_min = self._create_slider(0, 180, 0, self._on_slider_moved)
        self.s_h1_max, self.lbl_h1_max = self._create_slider(0, 180, 15, self._on_slider_moved)
        r1_grid.addWidget(QLabel("H1 Min:"), 0, 0)
        r1_grid.addWidget(self.s_h1_min, 0, 1)
        r1_grid.addWidget(self.lbl_h1_min, 0, 2)
        r1_grid.addWidget(QLabel("H1 Max:"), 1, 0)
        r1_grid.addWidget(self.s_h1_max, 1, 1)
        r1_grid.addWidget(self.lbl_h1_max, 1, 2)

        # Sat Min / Max
        self.s_s_min, self.lbl_s_min = self._create_slider(0, 255, 60, self._on_slider_moved)
        self.s_s_max, self.lbl_s_max = self._create_slider(0, 255, 255, self._on_slider_moved)
        r1_grid.addWidget(QLabel("Sat Min:"), 2, 0)
        r1_grid.addWidget(self.s_s_min, 2, 1)
        r1_grid.addWidget(self.lbl_s_min, 2, 2)
        r1_grid.addWidget(QLabel("Sat Max:"), 3, 0)
        r1_grid.addWidget(self.s_s_max, 3, 1)
        r1_grid.addWidget(self.lbl_s_max, 3, 2)

        # Val Min / Max
        self.s_v_min, self.lbl_v_min = self._create_slider(0, 255, 40, self._on_slider_moved)
        self.s_v_max, self.lbl_v_max = self._create_slider(0, 255, 255, self._on_slider_moved)
        r1_grid.addWidget(QLabel("Val Min:"), 4, 0)
        r1_grid.addWidget(self.s_v_min, 4, 1)
        r1_grid.addWidget(self.lbl_v_min, 4, 2)
        r1_grid.addWidget(QLabel("Val Max:"), 5, 0)
        r1_grid.addWidget(self.s_v_max, 5, 1)
        r1_grid.addWidget(self.lbl_v_max, 5, 2)

        controls_layout.addWidget(r1_box)

        # Range 2 Sliders (Hue 2 wrap-around for Red)
        r2_box = QGroupBox("HSV Thresholds: Range 2 (Red Wrap-around)")
        r2_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        r2_grid = QGridLayout(r2_box)

        self.s_h2_min, self.lbl_h2_min = self._create_slider(0, 180, 165, self._on_slider_moved)
        self.s_h2_max, self.lbl_h2_max = self._create_slider(0, 180, 180, self._on_slider_moved)
        r2_grid.addWidget(QLabel("H2 Min:"), 0, 0)
        r2_grid.addWidget(self.s_h2_min, 0, 1)
        r2_grid.addWidget(self.lbl_h2_min, 0, 2)
        r2_grid.addWidget(QLabel("H2 Max:"), 1, 0)
        r2_grid.addWidget(self.s_h2_max, 1, 1)
        r2_grid.addWidget(self.lbl_h2_max, 1, 2)
        controls_layout.addWidget(r2_box)

        # Contour Filters Box
        filter_box = QGroupBox("Shape Geometry Filters")
        filter_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        f_grid = QGridLayout(filter_box)

        self.s_area_min, self.lbl_area_min = self._create_slider(10, 300, 40, self._on_filter_moved)
        self.s_area_max, self.lbl_area_max = self._create_slider(300, 5000, 2500, self._on_filter_moved)
        self.s_circ_min, self.lbl_circ_min = self._create_slider(10, 90, 35, self._on_filter_moved)

        f_grid.addWidget(QLabel("Min Area:"), 0, 0)
        f_grid.addWidget(self.s_area_min, 0, 1)
        f_grid.addWidget(self.lbl_area_min, 0, 2)
        f_grid.addWidget(QLabel("Max Area:"), 1, 0)
        f_grid.addWidget(self.s_area_max, 1, 1)
        f_grid.addWidget(self.lbl_area_max, 1, 2)
        f_grid.addWidget(QLabel("Min Circularity:"), 2, 0)
        f_grid.addWidget(self.s_circ_min, 2, 1)
        f_grid.addWidget(self.lbl_circ_min, 2, 2)
        controls_layout.addWidget(filter_box)

        # Save Button
        self.btn_save_hsv = QPushButton("Save Thresholds to Config")
        self.btn_save_hsv.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_save_hsv.clicked.connect(self._save_clicked)
        controls_layout.addWidget(self.btn_save_hsv)

        main_layout.addWidget(controls_panel, stretch=2)

        # Right Column: Side-by-side Viewports (Rectified Table and Mask)
        views_panel = QFrame()
        views_layout = QVBoxLayout(views_panel)
        views_layout.setContentsMargins(0, 0, 0, 0)

        # Rectified Table View
        rect_group = QGroupBox("Rectified Color Feed")
        rect_group.setStyleSheet("color: #94a3b8; font-weight: bold;")
        rect_layout = QVBoxLayout(rect_group)
        self.lbl_rect_view = QLabel()
        self.lbl_rect_view.setMinimumSize(480, 280)
        self.lbl_rect_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_rect_view.setStyleSheet("background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px;")
        rect_layout.addWidget(self.lbl_rect_view)
        views_layout.addWidget(rect_group)

        # Binary Mask View
        mask_group = QGroupBox("Binary HSV Detection Mask")
        mask_group.setStyleSheet("color: #94a3b8; font-weight: bold;")
        mask_layout = QVBoxLayout(mask_group)
        self.lbl_mask_view = QLabel()
        self.lbl_mask_view.setMinimumSize(480, 280)
        self.lbl_mask_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_mask_view.setStyleSheet("background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px;")
        mask_layout.addWidget(self.lbl_mask_view)
        views_layout.addWidget(mask_group)

        main_layout.addWidget(views_panel, stretch=3)

    def _create_slider(self, min_val: int, max_val: int, init_val: int, callback):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(init_val)
        lbl = QLabel(str(init_val))
        lbl.setFixedWidth(35)
        slider.valueChanged.connect(lambda v: lbl.setText(str(v)))
        slider.valueChanged.connect(callback)
        return slider, lbl

    def _on_slider_moved(self) -> None:
        bounds = self.get_hsv_bounds()
        self.hsv_bounds_changed.emit(bounds)

    def _on_filter_moved(self) -> None:
        min_a = float(self.s_area_min.value())
        max_a = float(self.s_area_max.value())
        min_c = float(self.s_circ_min.value()) / 100.0
        self.contour_filters_changed.emit(min_a, max_a, min_c)

    def get_hsv_bounds(self) -> Dict[str, Any]:
        return {
            "dual_range": True,
            "lower1": [self.s_h1_min.value(), self.s_s_min.value(), self.s_v_min.value()],
            "upper1": [self.s_h1_max.value(), self.s_s_max.value(), self.s_v_max.value()],
            "lower2": [self.s_h2_min.value(), self.s_s_min.value(), self.s_v_min.value()],
            "upper2": [self.s_h2_max.value(), self.s_s_max.value(), self.s_v_max.value()],
        }

    def set_hsv_bounds(self, bounds: Dict[str, Any]) -> None:
        l1 = bounds.get("lower1", [0, 60, 40])
        u1 = bounds.get("upper1", [15, 255, 255])
        l2 = bounds.get("lower2", [165, 60, 40])
        u2 = bounds.get("upper2", [180, 255, 255])

        self.s_h1_min.setValue(int(l1[0]))
        self.s_s_min.setValue(int(l1[1]))
        self.s_v_min.setValue(int(l1[2]))
        self.s_h1_max.setValue(int(u1[0]))
        self.s_s_max.setValue(int(u1[1]))
        self.s_v_max.setValue(int(u1[2]))

        self.s_h2_min.setValue(int(l2[0]))
        self.s_h2_max.setValue(int(u2[0]))

    def _preset_orange(self) -> None:
        self.set_hsv_bounds({
            "lower1": [0, 60, 35], "upper1": [15, 255, 255],
            "lower2": [165, 60, 35], "upper2": [180, 255, 255]
        })
        self._on_slider_moved()

    def _preset_yellow(self) -> None:
        self.set_hsv_bounds({
            "lower1": [20, 100, 100], "upper1": [35, 255, 255],
            "lower2": [20, 100, 100], "upper2": [35, 255, 255]
        })
        self._on_slider_moved()

    def _preset_white(self) -> None:
        self.set_hsv_bounds({
            "lower1": [0, 0, 180], "upper1": [180, 50, 255],
            "lower2": [0, 0, 180], "upper2": [180, 50, 255]
        })
        self._on_slider_moved()

    def _save_clicked(self) -> None:
        self.save_requested.emit()
        QMessageBox.information(self, "Saved", "HSV Thresholds successfully saved to config.json!")

    def update_views(self, q_rect: QImage, q_mask: QImage) -> None:
        if not q_rect.isNull():
            pix = QPixmap.fromImage(q_rect)
            scaled = pix.scaled(self.lbl_rect_view.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
            self.lbl_rect_view.setPixmap(scaled)

        if not q_mask.isNull():
            pix = QPixmap.fromImage(q_mask)
            scaled = pix.scaled(self.lbl_mask_view.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
            self.lbl_mask_view.setPixmap(scaled)
