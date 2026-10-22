"""
Player Profiles and Lifetime Career Leaderboard Tab.
Maintains player rosters and computes historical win/loss standings and career statistics.
"""

from typing import List, Dict, Any
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFrame, QMessageBox, QGroupBox
)

from core.database import DatabaseManager


class PlayersTab(QWidget):
    """Player management and leaderboard view."""

    def __init__(self, db: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Top Bar: Add Player form
        add_bar = QFrame()
        add_bar.setStyleSheet("background-color: #1e293b; border-radius: 6px; padding: 6px;")
        ab_layout = QHBoxLayout(add_bar)

        ab_layout.addWidget(QLabel("New Player Name:"))
        self.txt_player_name = QLineEdit()
        self.txt_player_name.setPlaceholderText("e.g. Martin, Stepan, Vojta...")
        self.txt_player_name.setStyleSheet("background-color: #334155; color: white; padding: 4px 8px; border-radius: 4px;")
        ab_layout.addWidget(self.txt_player_name)

        self.btn_add_player = QPushButton("Register Player")
        self.btn_add_player.setStyleSheet("background-color: #16a34a; color: white; font-weight: bold; padding: 4px 14px; border-radius: 4px;")
        self.btn_add_player.clicked.connect(self._add_player_clicked)
        ab_layout.addWidget(self.btn_add_player)

        ab_layout.addStretch()

        self.btn_refresh = QPushButton("Refresh Leaderboard")
        self.btn_refresh.setStyleSheet("background-color: #475569; color: white; padding: 4px 12px; border-radius: 4px;")
        self.btn_refresh.clicked.connect(self.reload_leaderboard)
        ab_layout.addWidget(self.btn_refresh)

        main_layout.addWidget(add_bar)

        # Leaderboard Table
        group = QGroupBox("Foosball Lifetime Career Leaderboard")
        group.setStyleSheet("color: #94a3b8; font-weight: bold;")
        g_layout = QVBoxLayout(group)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Rank", "Player", "Matches", "Wins", "Losses", "Win Rate"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setStyleSheet("""
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
                padding: 6px;
            }
        """)
        g_layout.addWidget(self.table)
        main_layout.addWidget(group, stretch=1)

    def reload_leaderboard(self) -> None:
        """Fetches lifetime stats from database and populates table."""
        lb = self.db.get_leaderboard()
        self.table.setRowCount(0)

        for i, row_data in enumerate(lb):
            row = self.table.rowCount()
            self.table.insertRow(row)

            rank_item = QTableWidgetItem(f"#{i + 1}")
            rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            name_item = QTableWidgetItem(row_data["name"])
            matches_item = QTableWidgetItem(str(row_data["matches_played"]))
            matches_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            wins_item = QTableWidgetItem(str(row_data["wins"]))
            wins_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            losses_item = QTableWidgetItem(str(row_data["losses"]))
            losses_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            rate_item = QTableWidgetItem(f"{row_data['win_rate']:.1f}%")
            rate_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.table.setItem(row, 0, rank_item)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, matches_item)
            self.table.setItem(row, 3, wins_item)
            self.table.setItem(row, 4, losses_item)
            self.table.setItem(row, 5, rate_item)

    def _add_player_clicked(self) -> None:
        name = self.txt_player_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid player name.")
            return

        self.db.get_or_create_player(name)
        self.txt_player_name.clear()
        self.reload_leaderboard()
        QMessageBox.information(self, "Success", f"Player '{name}' registered successfully!")
