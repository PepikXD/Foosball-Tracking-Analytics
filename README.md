# Foosball Tracking & Player Analytics

A high-performance computer vision and analytics desktop application designed for automated foosball match tracking, perspective calibration, optical distortion correction, and player statistics aggregation.

Built according to the **Foosball Tracking & Player Analytics - Project Development Plan**.

---

## 🌟 Key Features

### 1. Computer Vision & Ingestion Pipeline
- **Dual Stream Ingestion (SYS-P0-01)**: Seamlessly toggle between local recorded match footage (`.MOV`, `.mp4`, `.avi`) and live UVC webcam devices up to 1080p60.
- **Interactive Perspective Calibration (SYS-P0-02)**: 4-point click-and-calibrate interface mapping table playfield corners to a canonical $1200 \times 700$ pixel top-down spatial plane.
- **Optical & Fisheye Distortion Correction (SYS-P2-02)**: Fast OpenCV remap unwarping ($k_1, k_2$ radial distortion coefficients) to straighten curved wide-angle action camera streams.
- **HSV Color Segmentation & Threshold Tuner (SYS-P0-03)**: Dual-range HSV filtering with real-time mask previews, supporting orange/red balls (hue wrap-around), yellow ITSF balls, and white balls.
- **Kalman Filter Tracking & Occlusion Recovery (SYS-P1-01)**: 4D kinematic state vector $[x, y, v_x, v_y]^T$ maintaining continuous smooth trajectory estimation across up to 15 occlusion frames when the ball passes beneath player figures or rods.
- **Ball Velocity & Speed Calculation (SYS-P1-02)**: Direct calculation and visual badge rendering of ball speed in km/h based on physical table scale calibration ($120 \text{ cm} \approx 1200 \text{ px}$).

### 2. Game Event Recognition (FSM)
- **Spatial Table Zone Partitioning (SYS-P0-05)**: 8 canonical rod zones, 2 goal pockets, and boundary wall collision detection.
- **Discrete Event Detection (SYS-P0-06)**:
  - **Goals**: Real-time goal detection when the ball crosses the goal plane with debounce lockout.
  - **Passes**: 5-bar to 3-bar controlled pass attempt, pass complete, and pass interception tracking.
  - **Shot Attempts**: High-velocity shots directed toward goal mouth.
  - **Possession Split**: Real-time rod and team possession tracking.

### 3. Analytics & UI Dashboard
- **Live Match Dashboard (SYS-P0-08)**: Live scoreboard, match clock, manual score overrides, ball speed meter, active rod indicator, and real-time event ticker.
- **Post-Match Summary & Report (SYS-P0-09)**: Match breakdown displaying possession %, shot volume, top shot speed, passing efficiency, and full event breakdown.
- **CSV Data Export (SYS-P2-03)**: One-click export of complete match events to structured CSV.
- **Player Profiles & Leaderboard (SYS-P1-05)**: Lifetime player tracking with win/loss standings and win percentages.
- **Relational SQLite Persistence (SYS-P0-07)**: Transaction-safe storage in `foosball.db` (`players`, `matches`, `match_players`, `game_events`).

---

## 📁 Repository Structure

```
.
├── config.json               # System configuration & calibration presets
├── requirements.txt          # Python dependencies
├── main.py                   # Application entry point
├── docs/
│   └── project_development_plan.md   # Full project design plan
├── core/
│   ├── config.py             # Config manager & preset loader
│   ├── fisheye.py            # Optical distortion unwarping
│   ├── homography.py         # Perspective 4-point homography
│   ├── detector.py           # Dual-range HSV ball segmentation
│   ├── kalman.py             # 4D Kalman filter & occlusion bridge
│   ├── zones.py              # 8-rod zone geometry
│   ├── fsm.py                # Finite state machine event detector
│   ├── database.py           # SQLite persistence layer
│   └── pipeline.py           # Unified vision pipeline
├── ui/
│   ├── app.py                # Main PyQt6 window
│   ├── video_worker.py       # Asynchronous video capture QThread
│   ├── dashboard_tab.py      # Live scoreboard & video viewer
│   ├── calibration_tab.py    # 4-point corner calibration UI
│   ├── hsv_tuner_tab.py      # Real-time HSV mask tuner
│   ├── fisheye_tab.py        # Fisheye parameter tuner
│   ├── summary_tab.py        # Post-match analytics & CSV export
│   └── players_tab.py        # Player career leaderboard
└── tests/
    └── test_core.py          # Unit test suite
```

---

## 🚀 Installation & Usage

### 1. Requirements
- Python 3.10+
- Dependencies: `PyQt6`, `opencv-python`, `numpy`, `pillow`

```bash
pip install -r requirements.txt
```

### 2. Running the App
Run the main script:
```bash
python main.py
```

### 3. Using the Test Videos
Presets are pre-configured in `config.json` for both test videos in `C:\Users\stepa\Desktop\TP_fotbalce`:

1. **Phone Camera (`2016_0126_042510_001.MOV`)**:
   - In the application menu, select **Presets -> Phone Camera (2016_0126)**.
   - Alternatively run:
     ```bash
     python main.py --preset phone_camera_2016_0126
     ```
2. **Action Camera with Fisheye (`2016_0127_045904_001.MOV`)**:
   - In the application menu, select **Presets -> Action Camera Fisheye (2016_0127)**.
   - Enables barrel distortion correction ($k_1 = -0.22, k_2 = 0.05$) to straighten curved lines.
   - Alternatively run:
     ```bash
     python main.py --preset action_camera_2016_0127
     ```

### 4. Running Tests
Run the automated unit test suite:
```bash
python -m unittest tests/test_core.py
```
