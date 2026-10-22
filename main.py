"""
Application Entry Point for Foosball Tracking & Player Analytics.
"""

import sys
import argparse
from PyQt6.QtWidgets import QApplication

from core.config import ConfigManager
from core.database import DatabaseManager
from ui.app import MainWindow


def main():
    parser = argparse.ArgumentParser(description="Foosball Tracking & Player Analytics")
    parser.add_argument("--config", default="config.json", help="Path to config.json")
    parser.add_argument("--db", default="foosball.db", help="Path to SQLite database")
    parser.add_argument("--video", default=None, help="Path to offline video file to load immediately")
    parser.add_argument("--preset", default=None, help="Preset key to apply (e.g. phone_camera_2016_0126, action_camera_2016_0127)")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Foosball Tracking & Player Analytics")

    cfg_mgr = ConfigManager(args.config)
    if args.preset:
        cfg_mgr.apply_preset(args.preset)
    if args.video:
        cfg_mgr.set("video_path", args.video)
        cfg_mgr.set("source_type", "file")
        cfg_mgr.save()

    db_mgr = DatabaseManager(args.db)

    window = MainWindow(cfg_mgr, db_mgr)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
