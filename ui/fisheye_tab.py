"""
Fisheye and Optical Lens Distortion Correction Tab.
Provides real-time sliders for radial distortion parameters (k1, k2) and focal scale,
enabling precise barrel unwarping for wide-angle action camera footage.
"""

from typing import Dict, Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QCheckBox, QGroupBox, QFrame, QGridLayout, QMessageBox
)


class FisheyeTab(QWidget):
    """Optical distortion tuner tab."""

    distortion_changed = pyqtSignal(float, float, bool, float)  # k1, k2, enabled, focal_scale
    save_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Controls Column
        controls_panel = QFrame()
        controls_panel.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 10px;")
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setSpacing(12)

        # Enable checkbox
        self.chk_enable = QCheckBox("Enable Fisheye Lens Correction")
        self.chk_enable.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 14px;")
        self.chk_enable.toggled.connect(self._on_values_changed)
        controls_layout.addWidget(self.chk_enable)

        # Presets Box
        preset_box = QGroupBox("Lens Presets")
        preset_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        preset_layout = QVBoxLayout(preset_box)

        self.btn_action_preset = QPushButton("Action Cam (Fisheye k1=-0.22)")
        self.btn_action_preset.setStyleSheet("background-color: #0369a1; color: white; padding: 4px; border-radius: 4px;")
        self.btn_action_preset.clicked.connect(self._preset_action)

        self.btn_phone_preset = QPushButton("Phone Camera (Disable Correction)")
        self.btn_phone_preset.setStyleSheet("background-color: #475569; color: white; padding: 4px; border-radius: 4px;")
        self.btn_phone_preset.clicked.connect(self._preset_phone)

        preset_layout.addWidget(self.btn_action_preset)
        preset_layout.addWidget(self.btn_phone_preset)
        controls_layout.addWidget(preset_box)

        # Parameters Box
        params_box = QGroupBox("Distortion Coefficients")
        params_box.setStyleSheet("color: #94a3b8; font-weight: bold;")
        params_grid = QGridLayout(params_box)

        # k1 slider: mapped from -50 to +20 -> / 100 -> -0.50 to +0.20
        self.s_k1 = QSlider(Qt.Orientation.Horizontal)
        self.s_k1.setRange(-50, 20)
        self.s_k1.setValue(-22)
        self.lbl_k1 = QLabel("-0.22")
        self.s_k1.valueChanged.connect(lambda v: self.lbl_k1.setText(f"{v / 100.0:.2f}"))
        self.s_k1.valueChanged.connect(self._on_values_changed)

        params_grid.addWidget(QLabel("k1 (Radial Barrel):"), 0, 0)
        params_grid.addWidget(self.s_k1, 0, 1)
        params_grid.addWidget(self.lbl_k1, 0, 2)

        # k2 slider: mapped from -20 to +20 -> / 100 -> -0.20 to +0.20
        self.s_k2 = QSlider(Qt.Orientation.Horizontal)
        self.s_k2.setRange(-20, 20)
        self.s_k2.setValue(5)
        self.lbl_k2 = QLabel("+0.05")
        self.s_k2.valueChanged.connect(lambda v: self.lbl_k2.setText(f"{v / 100.0:.2f}"))
        self.s_k2.valueChanged.connect(self._on_values_changed)

        params_grid.addWidget(QLabel("k2 (Secondary):"), 1, 0)
        params_grid.addWidget(self.s_k2, 1, 1)
        params_grid.addWidget(self.lbl_k2, 1, 2)

        # Focal scale: mapped from 50 to 150 -> / 100 -> 0.50 to 1.50
        self.s_focal = QSlider(Qt.Orientation.Horizontal)
        self.s_focal.setRange(50, 150)
        self.s_focal.setValue(90)
        self.lbl_focal = QLabel("0.90x")
        self.s_focal.valueChanged.connect(lambda v: self.lbl_focal.setText(f"{v / 100.0:.2f}x"))
        self.s_focal.valueChanged.connect(self._on_values_changed)

        params_grid.addWidget(QLabel("Focal Scale (FOV):"), 2, 0)
        params_grid.addWidget(self.s_focal, 2, 1)
        params_grid.addWidget(self.lbl_focal, 2, 2)

        controls_layout.addWidget(params_box)

        # Save Button
        self.btn_save = QPushButton("Save Fisheye Settings to Config")
        self.btn_save.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")
        self.btn_save.clicked.connect(self._save_clicked)
        controls_layout.addWidget(self.btn_save)

        controls_layout.addStretch()
        main_layout.addWidget(controls_panel, stretch=2)

        # Viewport Column: Raw / Undistorted Preview
        views_panel = QFrame()
        views_layout = QVBoxLayout(views_panel)
        views_layout.setContentsMargins(0, 0, 0, 0)

        preview_group = QGroupBox("Camera Stream Preview (With Distortion Correction)")
        preview_group.setStyleSheet("color: #94a3b8; font-weight: bold;")
        pg_layout = QVBoxLayout(preview_group)

        self.lbl_preview = QLabel()
        self.lbl_preview.setMinimumSize(640, 380)
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("background-color: #0b0f19; border: 1px solid #334155; border-radius: 4px;")
        pg_layout.addWidget(self.lbl_preview)

        views_layout.addWidget(preview_group)
        main_layout.addWidget(views_panel, stretch=3)

    def _on_values_changed(self) -> None:
        k1 = self.s_k1.value() / 100.0
        k2 = self.s_k2.value() / 100.0
        focal = self.s_focal.value() / 100.0
        enabled = self.chk_enable.isChecked()
        self.distortion_changed.emit(k1, k2, enabled, focal)

    def _preset_action(self) -> None:
        self.chk_enable.setChecked(True)
        self.s_k1.setValue(-22)
        self.s_k2.setValue(5)
        self.s_focal.setValue(90)
        self._on_values_changed()

    def _preset_phone(self) -> None:
        self.chk_enable.setChecked(False)
        self._on_values_changed()

    def _save_clicked(self) -> None:
        self.save_requested.emit()
        QMessageBox.information(self, "Saved", "Fisheye distortion parameters saved to config.json!")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_latest_qraw") and self._latest_qraw is not None and not self._latest_qraw.isNull():
            pix = QPixmap.fromImage(self._latest_qraw)
            scaled = pix.scaled(self.lbl_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
            self.lbl_preview.setPixmap(scaled)

    def update_frame(self, q_raw: QImage) -> None:
        self._latest_qraw = q_raw
        if not q_raw.isNull():
            pix = QPixmap.fromImage(q_raw)
            scaled = pix.scaled(self.lbl_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
            self.lbl_preview.setPixmap(scaled)
