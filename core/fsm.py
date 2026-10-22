"""
Finite State Machine (FSM) Event Detection Engine for Foosball Analytics.
Recognizes discrete gameplay events: Goal Scored, Shot Attempts, 5-to-3 Bar Passes,
Pass Interceptions, and Active Rod Possession.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
import time


class EventType(str, Enum):
    GOAL = "GOAL"
    SHOT_ATTEMPT = "SHOT_ATTEMPT"
    PASS_ATTEMPT = "PASS_ATTEMPT"
    PASS_COMPLETE = "PASS_COMPLETE"
    PASS_INTERCEPTED = "PASS_INTERCEPTED"
    POSSESSION_CHANGE = "POSSESSION_CHANGE"


@dataclass
class GameEvent:
    """Discrete game event payload emitted by the FSM."""
    timestamp_ms: int
    event_type: EventType
    team: str                 # 'A', 'B', or ''
    zone_id: str              # e.g. 'rod_4', 'goal_right'
    velocity_kmh: float = 0.0
    x: float = 0.0
    y: float = 0.0
    details: str = ""


class EventFSM:
    """State machine tracking possession transitions, passes, shots, and goals."""

    def __init__(self,
                 min_shot_speed_kmh: float = 12.0,
                 goal_lockout_seconds: float = 3.0,
                 pass_timeout_seconds: float = 1.5,
                 possession_min_frames: int = 4):

        self.min_shot_speed_kmh = min_shot_speed_kmh
        self.goal_lockout_seconds = goal_lockout_seconds
        self.pass_timeout_seconds = pass_timeout_seconds
        self.possession_min_frames = possession_min_frames

        # State tracking
        self.current_zone_id: Optional[str] = None
        self.zone_frame_counter: int = 0
        self.current_possession_team: Optional[str] = None
        self.current_possession_rod: Optional[str] = None

        # Pass tracking state: (team, timestamp_ms, source_rod, target_rod)
        self.pending_pass: Optional[Dict[str, Any]] = None

        # Shot tracking state
        self.last_shot_time_ms: int = 0

        # Goal debounce lockout
        self.last_goal_time_ms: int = -10000

        # Cumulative possession frames
        self.possession_frames_a: int = 0
        self.possession_frames_b: int = 0

    def reset(self) -> None:
        """Resets state machine at match kickoff."""
        self.current_zone_id = None
        self.zone_frame_counter = 0
        self.current_possession_team = None
        self.current_possession_rod = None
        self.pending_pass = None
        self.last_shot_time_ms = 0
        self.last_goal_time_ms = -10000
        self.possession_frames_a = 0
        self.possession_frames_b = 0

    def process_frame(self,
                      timestamp_ms: int,
                      x: float,
                      y: float,
                      vx: float,
                      vy: float,
                      speed_kmh: float,
                      is_tracking: bool,
                      zones) -> List[GameEvent]:
        """
        Evaluates current physical state against table geometry and FSM transitions.
        Returns a list of newly triggered discrete GameEvents.
        """
        events: List[GameEvent] = []

        if not is_tracking:
            return events

        zone_info = zones.get_zone(x, y)
        if zone_info is None:
            return events

        # ----------------------------------------------------
        # 1. Goal Detection with Debounce Lockout
        # ----------------------------------------------------
        elapsed_since_goal = (timestamp_ms - self.last_goal_time_ms) / 1000.0
        if elapsed_since_goal > self.goal_lockout_seconds:
            if zones.is_in_goal_left(x, y):
                # Ball inside left goal mouth -> Team B scores!
                self.last_goal_time_ms = timestamp_ms
                self.pending_pass = None
                events.append(GameEvent(
                    timestamp_ms=timestamp_ms,
                    event_type=EventType.GOAL,
                    team="B",
                    zone_id="goal_left",
                    velocity_kmh=speed_kmh,
                    x=x, y=y,
                    details="Goal scored for Team B in left pocket!"
                ))
                return events

            elif zones.is_in_goal_right(x, y):
                # Ball inside right goal mouth -> Team A scores!
                self.last_goal_time_ms = timestamp_ms
                self.pending_pass = None
                events.append(GameEvent(
                    timestamp_ms=timestamp_ms,
                    event_type=EventType.GOAL,
                    team="A",
                    zone_id="goal_right",
                    velocity_kmh=speed_kmh,
                    x=x, y=y,
                    details="Goal scored for Team A in right pocket!"
                ))
                return events

        # ----------------------------------------------------
        # 2. Possession Tracking
        # ----------------------------------------------------
        if zone_info.role != "goal":
            if zone_info.id == self.current_zone_id:
                self.zone_frame_counter += 1
            else:
                self.current_zone_id = zone_info.id
                self.zone_frame_counter = 1

            # Establish solid possession if residence frames >= threshold
            if self.zone_frame_counter >= self.possession_min_frames:
                new_team = zone_info.team
                new_rod = zone_info.id

                if new_team == "A":
                    self.possession_frames_a += 1
                else:
                    self.possession_frames_b += 1

                if new_team != self.current_possession_team or new_rod != self.current_possession_rod:
                    # Check pending pass resolution
                    if self.pending_pass is not None:
                        pass_team = self.pending_pass["team"]
                        pass_target = self.pending_pass["target_rod"]
                        if new_team == pass_team and new_rod == pass_target:
                            events.append(GameEvent(
                                timestamp_ms=timestamp_ms,
                                event_type=EventType.PASS_COMPLETE,
                                team=pass_team,
                                zone_id=new_rod,
                                velocity_kmh=speed_kmh,
                                x=x, y=y,
                                details=f"Successful 5-to-3 bar pass completed by Team {pass_team}!"
                            ))
                        elif new_team != pass_team:
                            events.append(GameEvent(
                                timestamp_ms=timestamp_ms,
                                event_type=EventType.PASS_INTERCEPTED,
                                team=new_team,
                                zone_id=new_rod,
                                velocity_kmh=speed_kmh,
                                x=x, y=y,
                                details=f"Pass intercepted by Team {new_team}!"
                            ))
                        self.pending_pass = None

                    # Emit possession change event
                    self.current_possession_team = new_team
                    self.current_possession_rod = new_rod
                    events.append(GameEvent(
                        timestamp_ms=timestamp_ms,
                        event_type=EventType.POSSESSION_CHANGE,
                        team=new_team,
                        zone_id=new_rod,
                        velocity_kmh=speed_kmh,
                        x=x, y=y,
                        details=f"Possession claimed by {zone_info.name}"
                    ))

        # Check pending pass timeout
        if self.pending_pass is not None:
            if (timestamp_ms - self.pending_pass["start_time"]) / 1000.0 > self.pass_timeout_seconds:
                self.pending_pass = None

        # ----------------------------------------------------
        # 3. Pass Attempt Detection (5-bar -> 3-bar)
        # ----------------------------------------------------
        # Team A 5-bar is rod_4 (x ~ 430-580), Team A 3-bar is rod_6 (x ~ 730-880). Ball moves Right (vx > 0)
        # Team B 5-bar is rod_5 (x ~ 580-730), Team B 3-bar is rod_3 (x ~ 280-430). Ball moves Left (vx < 0)
        if self.pending_pass is None and self.current_possession_rod is not None:
            if self.current_possession_rod == "rod_4" and zone_info.id == "rod_4" and vx > 40.0:
                self.pending_pass = {
                    "team": "A",
                    "source_rod": "rod_4",
                    "target_rod": "rod_6",
                    "start_time": timestamp_ms
                }
                events.append(GameEvent(
                    timestamp_ms=timestamp_ms,
                    event_type=EventType.PASS_ATTEMPT,
                    team="A",
                    zone_id="rod_4",
                    velocity_kmh=speed_kmh,
                    x=x, y=y,
                    details="Team A initiated 5-to-3 bar pass attempt!"
                ))
            elif self.current_possession_rod == "rod_5" and zone_info.id == "rod_5" and vx < -40.0:
                self.pending_pass = {
                    "team": "B",
                    "source_rod": "rod_5",
                    "target_rod": "rod_3",
                    "start_time": timestamp_ms
                }
                events.append(GameEvent(
                    timestamp_ms=timestamp_ms,
                    event_type=EventType.PASS_ATTEMPT,
                    team="B",
                    zone_id="rod_5",
                    velocity_kmh=speed_kmh,
                    x=x, y=y,
                    details="Team B initiated 5-to-3 bar pass attempt!"
                ))

        # ----------------------------------------------------
        # 4. Shot Attempt Detection
        # ----------------------------------------------------
        if speed_kmh >= self.min_shot_speed_kmh:
            # Shot toward Right Goal (Team A shot, vx > 0)
            if vx > 80.0 and (timestamp_ms - self.last_shot_time_ms) > 1000:
                # Originating from Team A 3-bar (rod_6) or 2-bar (rod_2) or 5-bar
                shooter_team = "A" if x < 950 else "B"
                self.last_shot_time_ms = timestamp_ms
                events.append(GameEvent(
                    timestamp_ms=timestamp_ms,
                    event_type=EventType.SHOT_ATTEMPT,
                    team=shooter_team,
                    zone_id=zone_info.id,
                    velocity_kmh=speed_kmh,
                    x=x, y=y,
                    details=f"Shot attempt by Team {shooter_team} at {speed_kmh:.1f} km/h!"
                ))
            # Shot toward Left Goal (Team B shot, vx < 0)
            elif vx < -80.0 and (timestamp_ms - self.last_shot_time_ms) > 1000:
                shooter_team = "B" if x > 250 else "A"
                self.last_shot_time_ms = timestamp_ms
                events.append(GameEvent(
                    timestamp_ms=timestamp_ms,
                    event_type=EventType.SHOT_ATTEMPT,
                    team=shooter_team,
                    zone_id=zone_info.id,
                    velocity_kmh=speed_kmh,
                    x=x, y=y,
                    details=f"Shot attempt by Team {shooter_team} at {speed_kmh:.1f} km/h!"
                ))

        return events

    def get_possession_split(self) -> Tuple[float, float]:
        """Returns possession percentage as (team_a_pct, team_b_pct)."""
        total = self.possession_frames_a + self.possession_frames_b
        if total == 0:
            return 50.0, 50.0
        pct_a = (self.possession_frames_a / total) * 100.0
        pct_b = (self.possession_frames_b / total) * 100.0
        return round(pct_a, 1), round(pct_b, 1)
