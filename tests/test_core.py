"""
Unit tests for Foosball Tracking & Player Analytics core modules.
"""

import os
import unittest
import numpy as np

from core.config import DEFAULT_CONFIG, ConfigManager
from core.fisheye import LensDistortionCorrector
from core.homography import HomographyTransformer
from core.detector import BallDetector
from core.kalman import FoosballKalmanFilter
from core.zones import TableZones
from core.fsm import EventFSM, EventType, GameEvent
from core.database import DatabaseManager


class TestCoreModules(unittest.TestCase):

    def test_homography_warp(self):
        """TC-VIS-01: Homography transform produces rectangular top-down view."""
        transformer = HomographyTransformer(700, 1200)
        points = [[100, 100], [1800, 120], [1750, 950], [120, 900]]
        self.assertTrue(transformer.set_points(points))
        self.assertTrue(transformer.is_calibrated())

        # Test point transform
        pt_rect = transformer.transform_point((100, 100))
        self.assertIsNotNone(pt_rect)
        self.assertAlmostEqual(pt_rect[0], 0.0, delta=2.0)
        self.assertAlmostEqual(pt_rect[1], 0.0, delta=2.0)

        # Test inverse point transform
        pt_inv = transformer.inverse_transform_point((0.0, 0.0))
        self.assertIsNotNone(pt_inv)
        self.assertAlmostEqual(pt_inv[0], 100.0, delta=2.0)
        self.assertAlmostEqual(pt_inv[1], 100.0, delta=2.0)

    def test_kalman_occlusion(self):
        """TC-VIS-02: Kalman filter maintains state during 10-frame occlusion."""
        kf = FoosballKalmanFilter(dt=1.0/30.0, max_occlusion_frames=15)
        # Train on 10 frames moving right at 300 px/s (10 px/frame)
        for i in range(10):
            kf.update((100.0 + i * 10.0, 350.0))

        self.assertTrue(kf.is_tracking)
        self.assertAlmostEqual(kf.X[1, 0], 350.0, delta=5.0)

        # Now simulate 10 occluded frames (measurement=None)
        for i in range(10):
            state = kf.update(None)
            self.assertTrue(state.is_tracking)
            self.assertTrue(state.is_occluded)
            self.assertEqual(state.occlusion_frames, i + 1)

        # After 10 occluded frames, target should still be tracking and position advanced
        self.assertTrue(kf.is_tracking)
        self.assertGreater(kf.X[0, 0], 190.0)

        # 16th occluded frame should exceed max_occlusion_frames and drop tracking
        for _ in range(6):
            state = kf.update(None)
        self.assertFalse(kf.is_tracking)

    def test_zones_and_fsm_goal(self):
        """TC-FSM-01: FSM emits GOAL event when ball enters goal mouth."""
        zones = TableZones()
        fsm = EventFSM(goal_lockout_seconds=1.0)

        # Ball in midfield
        events = fsm.process_frame(
            timestamp_ms=1000,
            x=350.0, y=600.0, vx=0.0, vy=0.0, speed_kmh=2.0,
            is_tracking=True, zones=zones
        )
        self.assertEqual(len(events), 0)

        # Ball shoots into Bottom Goal mouth (Team A scores)
        goal_events = fsm.process_frame(
            timestamp_ms=1200,
            x=350.0, y=1160.0, vx=0.0, vy=500.0, speed_kmh=25.0,
            is_tracking=True, zones=zones
        )
        self.assertEqual(len(goal_events), 1)
        self.assertEqual(goal_events[0].event_type, EventType.GOAL)
        self.assertEqual(goal_events[0].team, "A")

    def test_database_persistence(self):
        """TC-DAT-01: SQLite transaction wrapper preserves match events."""
        test_db = "test_foosball.db"
        if os.path.exists(test_db):
            os.remove(test_db)

        db = DatabaseManager(test_db)
        mid = db.start_match("Alpha", "Beta", "test.mp4", ["Alice"], ["Bob"])
        self.assertGreater(mid, 0)

        event = GameEvent(
            timestamp_ms=500,
            event_type=EventType.GOAL,
            team="A",
            zone_id="goal_bottom",
            velocity_kmh=22.5,
            x=350.0, y=1160.0,
            details="Great shot"
        )
        db.log_event(mid, event)
        db.update_match_score(mid, 1, 0)
        db.finish_match(mid, 1, 0, 45.0, 55.0, 45.0)

        summary = db.get_match_summary(mid)
        self.assertEqual(summary["match"]["score_a"], 1)
        self.assertEqual(summary["match"]["score_b"], 0)
        self.assertEqual(summary["team_a"]["score"], 1)

        # Test leaderboard
        lb = db.get_leaderboard()
        self.assertGreaterEqual(len(lb), 1)
        db.close()

        # Clean up
        try:
            if os.path.exists(test_db):
                os.remove(test_db)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
