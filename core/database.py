"""
Relational Database Persistence Layer for Foosball Tracking.
Provides thread-safe SQLite storage for Players, Matches, Lineups, and Game Events.
"""

import csv
import os
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
from core.fsm import GameEvent, EventType


class DatabaseManager:
    """Manages SQLite schema creation, match logging, and analytics aggregation."""

    def __init__(self, db_path: str = "foosball.db"):
        self.db_path = os.path.abspath(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def close(self) -> None:
        """Flushes WAL and checkpoint."""
        try:
            with self._get_connection() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        except Exception:
            pass

    def _init_db(self) -> None:
        """Initializes tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Players table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Matches table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_a_name TEXT NOT NULL,
                    team_b_name TEXT NOT NULL,
                    score_a INTEGER DEFAULT 0,
                    score_b INTEGER DEFAULT 0,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    status TEXT DEFAULT 'IN_PROGRESS',
                    video_source TEXT,
                    duration_seconds REAL DEFAULT 0.0,
                    possession_a REAL DEFAULT 50.0,
                    possession_b REAL DEFAULT 50.0
                );
            """)

            # Match Players link table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS match_players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                    team TEXT NOT NULL,
                    position TEXT,
                    UNIQUE(match_id, player_id, team)
                );
            """)

            # Timestamped Game Events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS game_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                    timestamp_ms INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    team TEXT,
                    zone_id TEXT,
                    velocity_kmh REAL DEFAULT 0.0,
                    x REAL DEFAULT 0.0,
                    y REAL DEFAULT 0.0,
                    details TEXT
                );
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_match ON game_events(match_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON game_events(event_type);")

    # -------------------------------------------------------------
    # Player Management
    # -------------------------------------------------------------
    def get_or_create_player(self, name: str, conn: Optional[sqlite3.Connection] = None) -> int:
        """Retrieves existing player ID or inserts a new player."""
        clean_name = name.strip()
        if not clean_name:
            clean_name = "Player"

        def _exec(c: sqlite3.Connection) -> int:
            cur = c.cursor()
            cur.execute("SELECT id FROM players WHERE name = ?;", (clean_name,))
            row = cur.fetchone()
            if row:
                return int(row["id"])
            cur.execute("INSERT INTO players (name) VALUES (?);", (clean_name,))
            return int(cur.lastrowid)

        if conn is not None:
            return _exec(conn)
        else:
            with self._get_connection() as c:
                return _exec(c)

    def list_players(self) -> List[Dict[str, Any]]:
        """Returns list of all registered players."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, created_at FROM players ORDER BY name ASC;")
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------
    # Match Management
    # -------------------------------------------------------------
    def start_match(self,
                    team_a_name: str = "Team Blue",
                    team_b_name: str = "Team Red",
                    video_source: str = "",
                    players_a: Optional[List[str]] = None,
                    players_b: Optional[List[str]] = None) -> int:
        """Records a new match session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO matches (team_a_name, team_b_name, video_source, status)
                VALUES (?, ?, ?, 'IN_PROGRESS');
            """, (team_a_name, team_b_name, video_source))
            match_id = int(cursor.lastrowid)

            if players_a:
                for p in players_a:
                    pid = self.get_or_create_player(p, conn=conn)
                    cursor.execute("""
                        INSERT OR IGNORE INTO match_players (match_id, player_id, team, position)
                        VALUES (?, ?, 'A', 'player');
                    """, (match_id, pid))

            if players_b:
                for p in players_b:
                    pid = self.get_or_create_player(p, conn=conn)
                    cursor.execute("""
                        INSERT OR IGNORE INTO match_players (match_id, player_id, team, position)
                        VALUES (?, ?, 'B', 'player');
                    """, (match_id, pid))

            return match_id

    def update_match_score(self, match_id: int, score_a: int, score_b: int) -> None:
        """Updates live score counters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE matches SET score_a = ?, score_b = ? WHERE id = ?;
            """, (score_a, score_b, match_id))

    def finish_match(self,
                     match_id: int,
                     score_a: int,
                     score_b: int,
                     duration_seconds: float,
                     possession_a: float,
                     possession_b: float) -> None:
        """Finalizes match stats and marks status as FINISHED."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE matches SET
                    score_a = ?,
                    score_b = ?,
                    duration_seconds = ?,
                    possession_a = ?,
                    possession_b = ?,
                    end_time = CURRENT_TIMESTAMP,
                    status = 'FINISHED'
                WHERE id = ?;
            """, (score_a, score_b, duration_seconds, possession_a, possession_b, match_id))

    # -------------------------------------------------------------
    # Event Logging
    # -------------------------------------------------------------
    def log_event(self, match_id: int, event: GameEvent) -> None:
        """Logs a single discrete game event in a transaction."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO game_events
                (match_id, timestamp_ms, event_type, team, zone_id, velocity_kmh, x, y, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                match_id,
                event.timestamp_ms,
                event.event_type.value,
                event.team,
                event.zone_id,
                event.velocity_kmh,
                event.x,
                event.y,
                event.details
            ))

    def get_match_events(self, match_id: int) -> List[Dict[str, Any]]:
        """Returns all events logged for a specific match."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp_ms, event_type, team, zone_id, velocity_kmh, details
                FROM game_events
                WHERE match_id = ?
                ORDER BY timestamp_ms ASC;
            """, (match_id,))
            return [dict(r) for r in cursor.fetchall()]

    # -------------------------------------------------------------
    # Match Summary & Analytics Aggregation
    # -------------------------------------------------------------
    def get_match_summary(self, match_id: int) -> Dict[str, Any]:
        """Calculates comprehensive post-match analytics report."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM matches WHERE id = ?;", (match_id,))
            match_row = cursor.fetchone()
            if not match_row:
                return {}

            m = dict(match_row)

            cursor.execute("""
                SELECT event_type, team, COUNT(*) as cnt, MAX(velocity_kmh) as max_v, AVG(velocity_kmh) as avg_v
                FROM game_events
                WHERE match_id = ?
                GROUP BY event_type, team;
            """, (match_id,))
            event_stats = cursor.fetchall()

            shots_a = 0
            shots_b = 0
            pass_att_a = 0
            pass_att_b = 0
            pass_cmp_a = 0
            pass_cmp_b = 0
            max_shot_speed_a = 0.0
            max_shot_speed_b = 0.0

            for es in event_stats:
                etype = es["event_type"]
                team = es["team"]
                cnt = es["cnt"]
                max_v = es["max_v"] or 0.0

                if etype == EventType.SHOT_ATTEMPT.value:
                    if team == "A":
                        shots_a += cnt
                        max_shot_speed_a = max(max_shot_speed_a, max_v)
                    else:
                        shots_b += cnt
                        max_shot_speed_b = max(max_shot_speed_b, max_v)
                elif etype == EventType.PASS_ATTEMPT.value:
                    if team == "A": pass_att_a += cnt
                    else: pass_att_b += cnt
                elif etype == EventType.PASS_COMPLETE.value:
                    if team == "A": pass_cmp_a += cnt
                    else: pass_cmp_b += cnt

            pass_acc_a = (pass_cmp_a / pass_att_a * 100.0) if pass_att_a > 0 else 0.0
            pass_acc_b = (pass_cmp_b / pass_att_b * 100.0) if pass_att_b > 0 else 0.0

            return {
                "match": m,
                "team_a": {
                    "name": m["team_a_name"],
                    "score": m["score_a"],
                    "possession_pct": m["possession_a"],
                    "shots": shots_a,
                    "max_shot_speed_kmh": round(max_shot_speed_a, 1),
                    "pass_attempts": pass_att_a,
                    "pass_completions": pass_cmp_a,
                    "pass_accuracy_pct": round(pass_acc_a, 1),
                },
                "team_b": {
                    "name": m["team_b_name"],
                    "score": m["score_b"],
                    "possession_pct": m["possession_b"],
                    "shots": shots_b,
                    "max_shot_speed_kmh": round(max_shot_speed_b, 1),
                    "pass_attempts": pass_att_b,
                    "pass_completions": pass_cmp_b,
                    "pass_accuracy_pct": round(pass_acc_b, 1),
                }
            }

    def export_match_csv(self, match_id: int, out_filepath: str) -> bool:
        """Exports all match events to a structured CSV file."""
        events = self.get_match_events(match_id)
        try:
            with open(out_filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp_ms", "Event_Type", "Team", "Zone", "Velocity_kmh", "Details"])
                for e in events:
                    writer.writerow([
                        e["timestamp_ms"],
                        e["event_type"],
                        e["team"],
                        e["zone_id"],
                        e["velocity_kmh"],
                        e["details"]
                    ])
            return True
        except Exception as ex:
            print(f"[DatabaseManager] Export CSV failed: {ex}")
            return False

    def get_leaderboard(self) -> List[Dict[str, Any]]:
        """Computes lifetime player statistics across all completed matches."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    p.id,
                    p.name,
                    COUNT(DISTINCT m.id) as matches_played,
                    SUM(CASE 
                        WHEN (mp.team = 'A' AND m.score_a > m.score_b) OR 
                             (mp.team = 'B' AND m.score_b > m.score_a) THEN 1 
                        ELSE 0 
                    END) as wins,
                    SUM(CASE 
                        WHEN (mp.team = 'A' AND m.score_a < m.score_b) OR 
                             (mp.team = 'B' AND m.score_b < m.score_a) THEN 1 
                        ELSE 0 
                    END) as losses
                FROM players p
                LEFT JOIN match_players mp ON p.id = mp.player_id
                LEFT JOIN matches m ON mp.match_id = m.id AND m.status = 'FINISHED'
                GROUP BY p.id, p.name
                ORDER BY wins DESC, matches_played DESC;
            """)
            rows = cursor.fetchall()
            leaderboard = []
            for r in rows:
                mp = r["matches_played"] or 0
                w = r["wins"] or 0
                l = r["losses"] or 0
                win_rate = (w / mp * 100.0) if mp > 0 else 0.0
                leaderboard.append({
                    "id": r["id"],
                    "name": r["name"],
                    "matches_played": mp,
                    "wins": w,
                    "losses": l,
                    "win_rate": round(win_rate, 1)
                })
            return leaderboard
