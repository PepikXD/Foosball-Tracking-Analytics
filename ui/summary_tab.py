"""
Post-Match Analytical Summary and CSV Export Tab.
Displays comprehensive match breakdown: score, possession split %, shot volume & top speed,
5-to-3 bar passing efficiency, timeline table, and CSV export.
"""

from typing import Dict, Any, List, Optional
import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QGridLayout, QFileDialog, QMessageBox, QGroupBox
)

from core.database import DatabaseManager


class SummaryTab(QWidget):
    """Post-Match Analytical Report Tab."""

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self.current_match_id: Optional[int] = None
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Match Selection Header
        header_frame = QFrame()
        header_frame.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 6px;")
        h_layout = QHBoxLayout(header_frame)

        h_layout.addWidget(QLabel("Select Match:"))
        self.combo_matches = QComboBox()
        self.combo_matches.setStyleSheet("background-color: #334155; color: white; padding: 4px 10px; border-radius: 4px;")
        self.combo_matches.currentIndexChanged.connect(self._on_match_selected)
        h_layout.addWidget(self.combo_matches)

        self.btn_refresh = QPushButton("Refresh List")
        self.btn_refresh.setStyleSheet("background-color: #475569; color: white; padding: 4px 12px; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.reload_matches)
        h_layout.addWidget(self.btn_refresh)

        h_layout.addStretch()

        self.btn_export_csv = QPushButton("Export Match to CSV")
        self.btn_export_csv.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 4px 14px; border-radius: 4px;")
        self.btn_export_csv.clicked.connect(self._export_csv_clicked)
        h_layout.addWidget(self.btn_export_csv)

        main_layout.addWidget(header_frame)

        # Analytics Overview Cards
        cards_grid = QGridLayout()

        # Score Card
        self.card_score = self._create_card("FINAL SCORE", "0 - 0", "#38bdf8")
        cards_grid.addWidget(self.card_score, 0, 0)

        # Possession Card
        self.card_poss = self._create_card("POSSESSION SPLIT", "50% - 50%", "#facc15")
        cards_grid.addWidget(self.card_poss, 0, 1)

        # Shots Card
        self.card_shots = self._create_card("SHOTS (A / B)", "0 / 0", "#f87171")
        cards_grid.addWidget(self.card_shots, 0, 2)

        # Top Speed Card
        self.card_speed = self._create_card("TOP SHOT SPEED", "0.0 km/h", "#e879f9")
        cards_grid.addWidget(self.card_speed, 1, 0)

        # Passing Accuracy Team A
        self.card_pass_a = self._create_card("TEAM A PASS ACCURACY", "0.0% (0/0)", "#4ade80")
        cards_grid.addWidget(self.card_pass_a, 1, 1)

        # Passing Accuracy Team B
        self.card_pass_b = self._create_card("TEAM B PASS ACCURACY", "0.0% (0/0)", "#4ade80")
        cards_grid.addWidget(self.card_pass_b, 1, 2)

        main_layout.addLayout(cards_grid)

        # Event Log Breakdown Table
        table_group = QGroupBox("Complete Chronological Match Event Log")
        table_group.setStyleSheet("color: #94a3b8; font-weight: bold;")
        t_layout = QVBoxLayout(table_group)

        self.event_table = QTableWidget(0, 5)
        self.event_table.setHorizontalHeaderLabels(["Timestamp", "Event Type", "Team", "Zone", "Speed (km/h)"])
        self.event_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.event_table.setStyleSheet("""
            QTableWidget {
                background-color: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 4px;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                font-weight: bold;
                border: none;
                padding: 4px;
            }
        """)
        t_layout.addWidget(self.event_table)
        main_layout.addWidget(table_group, stretch=1)

    def _create_card(self, title: str, initial_val: str, color_hex: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 10px;")
        l = QVBoxLayout(card)
        l.setContentsMargins(6, 6, 6, 6)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        lbl_v = QLabel(initial_val)
        lbl_v.setObjectName("cardVal")
        lbl_v.setStyleSheet(f"color: {color_hex}; font-size: 20px; font-weight: bold;")

        l.addWidget(lbl_t)
        l.addWidget(lbl_v)
        return card

    def _set_card_val(self, card: QFrame, val: str) -> None:
        lbl = card.findChild(QLabel, "cardVal")
        if lbl:
            lbl.setText(val)

    def reload_matches(self) -> None:
        """Fetches all matches from SQLite database and updates dropdown."""
        self.combo_matches.blockSignals(True)
        self.combo_matches.clear()

        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, team_a_name, team_b_name, score_a, score_b, start_time FROM matches ORDER BY id DESC;")
                rows = cursor.fetchall()

                for r in rows:
                    text = f"Match #{r['id']}: {r['team_a_name']} ({r['score_a']}) vs {r['team_b_name']} ({r['score_b']}) - {r['start_time'][:16]}"
                    self.combo_matches.addItem(text, r["id"])

        except Exception as e:
            print(f"[SummaryTab] Error querying matches: {e}")

        self.combo_matches.blockSignals(False)
        if self.combo_matches.count() > 0:
            self._on_match_selected(0)

    def _on_match_selected(self, idx: int) -> None:
        match_id = self.combo_matches.currentData()
        if match_id is None:
            return

        self.current_match_id = int(match_id)
        self.display_match(self.current_match_id)

    def display_match(self, match_id: int) -> None:
        """Fetches and populates summary cards and event table for the specified match."""
        summary = self.db.get_match_summary(match_id)
        if not summary:
            return

        m = summary["match"]
        ta = summary["team_a"]
        tb = summary["team_b"]

        self._set_card_val(self.card_score, f"{m['score_a']} - {m['score_b']}")
        self._set_card_val(self.card_poss, f"{ta['possession_pct']}% - {tb['possession_pct']}%")
        self._set_card_val(self.card_shots, f"{ta['shots']} / {tb['shots']}")

        max_speed = max(ta["max_shot_speed_kmh"], tb["max_shot_speed_kmh"])
        self._set_card_val(self.card_speed, f"{max_speed:.1f} km/h")

        self._set_card_val(self.card_pass_a, f"{ta['pass_accuracy_pct']}% ({ta['pass_completions']}/{ta['pass_attempts']})")
        self._set_card_val(self.card_pass_b, f"{tb['pass_accuracy_pct']}% ({tb['pass_completions']}/{tb['pass_attempts']})")

        # Load events table
        events = self.db.get_match_events(match_id)
        self.event_table.setRowCount(0)

        for e in events:
            row = self.event_table.rowCount()
            self.event_table.insertRow(row)

            sec = e["timestamp_ms"] / 1000.0
            time_str = f"{int(sec // 60):02d}:{int(sec % 60):02d}"

            self.event_table.setItem(row, 0, QTableWidgetItem(time_str))
            self.event_table.setItem(row, 1, QTableWidgetItem(e["event_type"]))
            self.event_table.setItem(row, 2, QTableWidgetItem(e["team"] or ""))
            self.event_table.setItem(row, 3, QTableWidgetItem(e["zone_id"] or ""))
            self.event_table.setItem(row, 4, QTableWidgetItem(f"{e['velocity_kmh']:.1f}"))

    def _export_csv_clicked(self) -> None:
        if self.current_match_id is None:
            QMessageBox.warning(self, "No Match", "Please select a match before exporting.")
            return

        filename, _ = QFileDialog.getSaveFileName(self, "Save Match CSV", f"match_{self.current_match_id}_events.csv", "CSV Files (*.csv)")
        if filename:
            if self.db.export_match_csv(self.current_match_id, filename):
                QMessageBox.information(self, "Exported", f"Successfully exported match events to:\n{filename}")
            else:
                QMessageBox.critical(self, "Error", "Failed to export CSV.")
