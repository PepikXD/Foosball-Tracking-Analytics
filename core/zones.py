"""
Table Zone Partitioning Model for Foosball Analytics.
Defines canonical 8-rod zone partitions, goal mouth geometries, and out-of-bounds walls
on a normalized 1200 x 700 top-down playing surface.
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
    x_min: float
    x_max: float
    y_min: float = 0.0
    y_max: float = 700.0


class TableZones:
    """Manages spatial zone mapping and goal mouth detection."""

    def __init__(self, zones_config: Optional[Dict[str, Any]] = None):
        self.width = 1200
        self.height = 700

        # Goal mouths centered on left and right borders
        self.goal_left = {"x_min": 0, "x_max": 65, "y_min": 210, "y_max": 490}
        self.goal_right = {"x_min": 1135, "x_max": 1200, "y_min": 210, "y_max": 490}

        self.rods: List[ZoneInfo] = []
        if zones_config:
            self._load_from_config(zones_config)
        else:
            self._init_defaults()

    def _init_defaults(self) -> None:
        """Initializes default 8-rod partitions matching standard Tornado ITSF layouts."""
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
        gl = cfg.get("goal_left", {})
        if gl:
            self.goal_left = {
                "x_min": gl.get("x_min", 0), "x_max": gl.get("x_max", 65),
                "y_min": gl.get("y_min", 210), "y_max": gl.get("y_max", 490)
            }
        gr = cfg.get("goal_right", {})
        if gr:
            self.goal_right = {
                "x_min": gr.get("x_min", 1135), "x_max": gr.get("x_max", 1200),
                "y_min": gr.get("y_min", 210), "y_max": gr.get("y_max", 490)
            }

        self.rods = []
        for r in cfg.get("rods", []):
            self.rods.append(ZoneInfo(
                id=r["id"],
                name=r["name"],
                team=r["team"],
                role=r["role"],
                x_min=float(r["x_min"]),
                x_max=float(r["x_max"]),
                y_min=float(r.get("y_min", 0.0)),
                y_max=float(r.get("y_max", 700.0))
            ))

    def is_in_goal_left(self, x: float, y: float) -> bool:
        """Checks if coordinate falls inside Team A's goal mouth (Team B scores)."""
        gl = self.goal_left
        return gl["x_min"] <= x <= gl["x_max"] and gl["y_min"] <= y <= gl["y_max"]

    def is_in_goal_right(self, x: float, y: float) -> bool:
        """Checks if coordinate falls inside Team B's goal mouth (Team A scores)."""
        gr = self.goal_right
        return gr["x_min"] <= x <= gr["x_max"] and gr["y_min"] <= y <= gr["y_max"]

    def get_zone(self, x: float, y: float) -> Optional[ZoneInfo]:
        """Returns the specific rod zone containing coordinate (x, y)."""
        if self.is_in_goal_left(x, y):
            return ZoneInfo("goal_left", "Goal A (Left)", "A", "goal",
                            self.goal_left["x_min"], self.goal_left["x_max"],
                            self.goal_left["y_min"], self.goal_left["y_max"])
        if self.is_in_goal_right(x, y):
            return ZoneInfo("goal_right", "Goal B (Right)", "B", "goal",
                            self.goal_right["x_min"], self.goal_right["x_max"],
                            self.goal_right["y_min"], self.goal_right["y_max"])

        for rod in self.rods:
            if rod.x_min <= x < rod.x_max and rod.y_min <= y <= rod.y_max:
                return rod

        return None

    def draw_zones(self, frame: np.ndarray, alpha: float = 0.25) -> np.ndarray:
        """Draws subtle color-coded zone overlays onto the rectified 1200x700 canvas."""
        overlay = frame.copy()

        # Goal areas (flashing red / dark gray)
        cv2.rectangle(
            overlay,
            (int(self.goal_left["x_min"]), int(self.goal_left["y_min"])),
            (int(self.goal_left["x_max"]), int(self.goal_left["y_max"])),
            (0, 0, 180), -1
        )
        cv2.rectangle(
            overlay,
            (int(self.goal_right["x_min"]), int(self.goal_right["y_min"])),
            (int(self.goal_right["x_max"]), int(self.goal_right["y_max"])),
            (0, 0, 180), -1
        )

        # Rod zones
        for i, rod in enumerate(self.rods):
            # Team A = Blue tinted, Team B = Orange/Yellow tinted
            color = (180, 80, 40) if rod.team == "A" else (40, 120, 200)
            cv2.line(overlay, (int(rod.x_min), 0), (int(rod.x_min), self.height), color, 1)

        cv2.addWeighted(overlay, alpha, frame, 1.0 - alpha, 0, frame)

        # Border and text labels
        cv2.rectangle(frame, (0, 0), (self.width - 1, self.height - 1), (255, 255, 255), 1)
        for rod in self.rods:
            center_x = int((rod.x_min + rod.x_max) / 2)
            label = f"{rod.team}-{rod.role[:3].upper()}"
            cv2.putText(frame, label, (center_x - 20, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (220, 220, 220), 1, cv2.LINE_AA)

        return frame
