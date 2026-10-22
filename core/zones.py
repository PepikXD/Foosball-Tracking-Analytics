"""
Table Zone Partitioning Model for Foosball Analytics.
Defines canonical 8-rod zone partitions, goal mouth geometries, and out-of-bounds walls
on a normalized 700 x 1200 vertical top-down playing surface.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import cv2
import numpy as np


@dataclass
class ZoneInfo:
    """Represents a discrete playing zone on the foosball table."""
    id: str
    name: str
    team: str       # 'A' or 'B'
    role: str       # 'goalie', 'defense', 'midfield', 'offense', 'goal'
    y_min: float
    y_max: float
    x_min: float = 0.0
    x_max: float = 700.0


class TableZones:
    """Manages spatial zone mapping and goal mouth detection on vertical 700x1200 canvas."""

    def __init__(self, zones_config: Optional[Dict[str, Any]] = None):
        self.width = 700
        self.height = 1200

        # Goal mouths at top and bottom ends
        self.goal_top = {"x_min": 210, "x_max": 490, "y_min": 0, "y_max": 65}
        self.goal_bottom = {"x_min": 210, "x_max": 490, "y_min": 1135, "y_max": 1200}

        self.rods: List[ZoneInfo] = []
        if zones_config:
            self._load_from_config(zones_config)
        else:
            self._init_defaults()

    def _init_defaults(self) -> None:
        """Initializes default 8-rod vertical partitions matching standard Tornado ITSF layouts."""
        self.rods = [
            ZoneInfo("rod_1", "Team A Goalie", "A", "goalie",   50.0, 160.0),
            ZoneInfo("rod_2", "Team A 2-Bar",  "A", "defense",  160.0, 280.0),
            ZoneInfo("rod_3", "Team B 3-Bar",  "B", "offense",  280.0, 430.0),
            ZoneInfo("rod_4", "Team A 5-Bar",  "A", "midfield", 430.0, 580.0),
            ZoneInfo("rod_5", "Team B 5-Bar",  "B", "midfield", 580.0, 730.0),
            ZoneInfo("rod_6", "Team A 3-Bar",  "A", "offense",  730.0, 880.0),
            ZoneInfo("rod_7", "Team B 2-Bar",  "B", "defense",  880.0, 1000.0),
            ZoneInfo("rod_8", "Team B Goalie", "B", "goalie",  1000.0, 1140.0),
        ]

    def _load_from_config(self, cfg: Dict[str, Any]) -> None:
        """Loads customized zone bounds from configuration dictionary."""
        gt = cfg.get("goal_top", cfg.get("goal_left", {}))
        if gt:
            self.goal_top = {
                "x_min": gt.get("x_min", 210), "x_max": gt.get("x_max", 490),
                "y_min": gt.get("y_min", 0), "y_max": gt.get("y_max", 65)
            }
        gb = cfg.get("goal_bottom", cfg.get("goal_right", {}))
        if gb:
            self.goal_bottom = {
                "x_min": gb.get("x_min", 210), "x_max": gb.get("x_max", 490),
                "y_min": gb.get("y_min", 1135), "y_max": gb.get("y_max", 1200)
            }

        self.rods = []
        for r in cfg.get("rods", []):
            self.rods.append(ZoneInfo(
                id=r["id"],
                name=r["name"],
                team=r["team"],
                role=r["role"],
                y_min=float(r.get("y_min", r.get("x_min", 0.0))),
                y_max=float(r.get("y_max", r.get("x_max", 700.0))),
                x_min=0.0,
                x_max=700.0
            ))

    def is_in_goal_top(self, x: float, y: float) -> bool:
        """Checks if coordinate falls inside Team A's goal mouth (Top end, Team B scores)."""
        gt = self.goal_top
        return gt["x_min"] <= x <= gt["x_max"] and gt["y_min"] <= y <= gt["y_max"]

    def is_in_goal_bottom(self, x: float, y: float) -> bool:
        """Checks if coordinate falls inside Team B's goal mouth (Bottom end, Team A scores)."""
        gb = self.goal_bottom
        return gb["x_min"] <= x <= gb["x_max"] and gb["y_min"] <= y <= gb["y_max"]

    # Alias methods for compatibility
    def is_in_goal_left(self, x: float, y: float) -> bool:
        return self.is_in_goal_top(x, y)

    def is_in_goal_right(self, x: float, y: float) -> bool:
        return self.is_in_goal_bottom(x, y)

    def get_zone(self, x: float, y: float) -> Optional[ZoneInfo]:
        """Returns the specific rod zone containing coordinate (x, y)."""
        if self.is_in_goal_top(x, y):
            return ZoneInfo("goal_top", "Goal A (Top)", "A", "goal",
                            self.goal_top["y_min"], self.goal_top["y_max"],
                            self.goal_top["x_min"], self.goal_top["x_max"])
        if self.is_in_goal_bottom(x, y):
            return ZoneInfo("goal_bottom", "Goal B (Bottom)", "B", "goal",
                            self.goal_bottom["y_min"], self.goal_bottom["y_max"],
                            self.goal_bottom["x_min"], self.goal_bottom["x_max"])

        for rod in self.rods:
            if rod.y_min <= y < rod.y_max and rod.x_min <= x <= rod.x_max:
                return rod

        return None

    def draw_zones(self, frame: np.ndarray, alpha: float = 0.25) -> np.ndarray:
        """Draws subtle color-coded zone overlays onto the rectified 700x1200 canvas."""
        overlay = frame.copy()

        # Goal areas (flashing red / dark gray)
        cv2.rectangle(
            overlay,
            (int(self.goal_top["x_min"]), int(self.goal_top["y_min"])),
            (int(self.goal_top["x_max"]), int(self.goal_top["y_max"])),
            (0, 0, 180), -1
        )
        cv2.rectangle(
            overlay,
            (int(self.goal_bottom["x_min"]), int(self.goal_bottom["y_min"])),
            (int(self.goal_bottom["x_max"]), int(self.goal_bottom["y_max"])),
            (0, 0, 180), -1
        )

        # Rod horizontal partition lines
        for rod in self.rods:
            color = (180, 80, 40) if rod.team == "A" else (40, 120, 200)
            cv2.line(overlay, (0, int(rod.y_min)), (self.width, int(rod.y_min)), color, 1)

        cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

        # Border and text labels
        cv2.rectangle(frame, (0, 0), (self.width - 1, self.height - 1), (255, 255, 255), 1)
        for rod in self.rods:
            center_y = int((rod.y_min + rod.y_max) / 2)
            label = f"{rod.team}-{rod.role[:3].upper()}"
            cv2.putText(frame, label, (12, center_y + 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)

        return frame
