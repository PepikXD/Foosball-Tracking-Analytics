"""
Configuration manager for Foosball Tracking & Player Analytics.
Handles serialization and deserialization of system settings, calibration matrices,
camera sources, HSV thresholds, and zone definitions to/from config.json.
"""

import json
import os
from typing import Dict, Any, List

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "1.1.0",
    "target_resolution": [700, 1200],  # Vertical Table: 700 width x 1200 height
    "pixels_per_cm": 10.0,             # 1200px = 120cm table length -> 10 px/cm
    
    # Active video source (filepath string or int index for webcam)
    "source_type": "file",
    "video_path": r"C:\Users\stepa\Desktop\TP_fotbalce\2016_0126_042510_001.MOV",
    "camera_index": 0,
    
    # Fisheye / Radial Lens Distortion Correction
    "fisheye": {
        "enabled": False,
        "k1": -0.22,
        "k2": 0.05,
        "p1": 0.0,
        "p2": 0.0,
        "focal_scale": 0.9,
    },
    
    # Homography 4 Playfield Corners [x, y] in clockwise order for Vertical Table:
    # 1. Top-Left (0, 0), 2. Top-Right (700, 0), 3. Bottom-Right (700, 1200), 4. Bottom-Left (0, 1200)
    "calibration_points": [
        [870, 650],   # Top-Left (Team A / Black goal side, left wall)
        [720, 135],   # Top-Right (Team A / Black goal side, right wall)
        [1730, 15],   # Bottom-Right (Team B / Yellow goal side, right wall)
        [1895, 785]   # Bottom-Left (Team B / Yellow goal side, left wall)
    ],
    
    # Presets for the two test videos
    "presets": {
        "phone_camera_2016_0126": {
            "name": "Phone Camera (2016_0126)",
            "video_path": r"C:\Users\stepa\Desktop\TP_fotbalce\2016_0126_042510_001.MOV",
            "fisheye_enabled": False,
            "k1": 0.0,
            "k2": 0.0,
            "calibration_points": [
                [870, 650],
                [720, 135],
                [1730, 15],
                [1895, 785]
            ],
            "hsv_bounds": {
                "lower1": [0, 60, 40],
                "upper1": [15, 255, 255],
                "lower2": [165, 60, 40],
                "upper2": [180, 255, 255],
                "dual_range": True
            }
        },
        "action_camera_2016_0127": {
            "name": "Action Camera Fisheye (2016_0127)",
            "video_path": r"C:\Users\stepa\Desktop\TP_fotbalce\2016_0127_045904_001.MOV",
            "fisheye_enabled": True,
            "k1": -0.22,
            "k2": 0.05,
            "calibration_points": [
                [805, 845],
                [675, 205],
                [1560, 85],
                [1690, 720]
            ],
            "hsv_bounds": {
                "lower1": [0, 60, 35],
                "upper1": [15, 255, 255],
                "lower2": [165, 60, 35],
                "upper2": [180, 255, 255],
                "dual_range": True
            }
        }
    },
    
    # HSV Ball Detection Thresholds
    "hsv_bounds": {
        "dual_range": True,
        "lower1": [0, 60, 40],
        "upper1": [15, 255, 255],
        "lower2": [165, 60, 40],
        "upper2": [180, 255, 255],
    },
    
    # Contour Filtering
    "contour_filter": {
        "min_area": 40.0,
        "max_area": 2500.0,
        "min_circularity": 0.35,
        "morph_kernel_size": 3,
    },
    
    # Kalman Filter Configuration
    "kalman": {
        "max_occlusion_frames": 15,
        "process_noise_pos": 1e-2,
        "process_noise_vel": 5.0,
        "measurement_noise": 1.0,
        "max_prediction_distance": 180.0,
        "motion_trail_length": 25,
    },
    
    # Vertical Field Zones (Canonical 700 width x 1200 height space)
    # Rod zones divide the Y axis from 0 to 1200
    "zones": {
        "goal_top": {"x_min": 210, "x_max": 490, "y_min": 0, "y_max": 65},
        "goal_bottom": {"x_min": 210, "x_max": 490, "y_min": 1135, "y_max": 1200},
        "rods": [
            {"id": "rod_1", "name": "Team A Goalie", "team": "A", "role": "goalie", "y_min": 50, "y_max": 160},
            {"id": "rod_2", "name": "Team A 2-Bar",  "team": "A", "role": "defense", "y_min": 160, "y_max": 280},
            {"id": "rod_3", "name": "Team B 3-Bar",  "team": "B", "role": "offense", "y_min": 280, "y_max": 430},
            {"id": "rod_4", "name": "Team A 5-Bar",  "team": "A", "role": "midfield", "y_min": 430, "y_max": 580},
            {"id": "rod_5", "name": "Team B 5-Bar",  "team": "B", "role": "midfield", "y_min": 580, "y_max": 730},
            {"id": "rod_6", "name": "Team A 3-Bar",  "team": "A", "role": "offense", "y_min": 730, "y_max": 880},
            {"id": "rod_7", "name": "Team B 2-Bar",  "team": "B", "role": "defense", "y_min": 880, "y_max": 1000},
            {"id": "rod_8", "name": "Team B Goalie", "team": "B", "role": "goalie", "y_min": 1000, "y_max": 1140},
        ]
    },
    
    # Event FSM thresholds
    "fsm": {
        "min_shot_speed_kmh": 12.0,
        "goal_lockout_seconds": 3.0,
        "pass_timeout_seconds": 1.5,
        "possession_min_frames": 5,
    }
}


class ConfigManager:
    """Manages application configuration with disk persistence."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = os.path.abspath(config_path)
        self.data: Dict[str, Any] = self.load()

    def load(self) -> Dict[str, Any]:
        """Loads config from JSON file or returns defaults if not present."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    config = DEFAULT_CONFIG.copy()
                    config.update(loaded)
                    return config
            except Exception as e:
                print(f"[ConfigManager] Warning: failed to parse {self.config_path}: {e}")
        return DEFAULT_CONFIG.copy()

    def save(self) -> bool:
        """Saves current configuration to disk."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)
            return True
        except Exception as e:
            print(f"[ConfigManager] Error writing config: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def apply_preset(self, preset_key: str) -> bool:
        """Applies a named preset to the active configuration."""
        presets = self.data.get("presets", {})
        if preset_key not in presets:
            return False
        p = presets[preset_key]
        if "video_path" in p:
            self.data["video_path"] = p["video_path"]
        if "fisheye_enabled" in p:
            self.data["fisheye"]["enabled"] = p["fisheye_enabled"]
        if "k1" in p:
            self.data["fisheye"]["k1"] = p["k1"]
        if "k2" in p:
            self.data["fisheye"]["k2"] = p["k2"]
        if "calibration_points" in p:
            self.data["calibration_points"] = p["calibration_points"]
        if "hsv_bounds" in p:
            self.data["hsv_bounds"] = p["hsv_bounds"]
        self.save()
        return True
