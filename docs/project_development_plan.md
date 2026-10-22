# Foosball Tracking & Player Analytics - Project Development Plan

## 1. Executive Summary & System Architecture

The **Foosball Tracking & Player Analytics** system is a high-performance computer vision and analytics desktop application designed to capture, rectify, track, and analyze foosball matches in real time.

```
+-----------------------------------------------------------------------------------------+
|                            VIDEO PROCESSING WORKER THREAD                               |
|                                                                                         |
|  [Stream Source]  --->  [Lens Distortion]  --->  [Homography Transform]                 |
|  (Camera / File)        (Fisheye Unwarp)         (1200x700 Top-Down)                    |
|                                                          |                              |
|                                                          v                              |
|  [Event FSM]      <---  [Table Zones]     <---  [Kalman Filter]   <---  [HSV Ball Det]  |
|  (Goal, Pass,           (8-Bar Model)           (Occlusion Pred)        (Color + Cont)  |
|   Shot, Poss)                                                                           |
+-----------------------------------------------------------------------------------------+
                                           |
                                    Thread Signals
                                           v
+-----------------------------------------------------------------------------------------+
|                                    MAIN UI THREAD                                       |
|                                                                                         |
|  - Live Match Dashboard (Scoreboard, Timer, Speed, Possession, Video Feeds)             |
|  - Interactive 4-Point Homography Calibration Canvas                                    |
|  - Real-Time HSV Color Mask Tuning Utility                                              |
|  - Fisheye Barrel Distortion Calibrator                                                 |
|  - Analytical Match Summary & CSV Exporter                                              |
|  - SQLite Database Store (Players, Matches, Game Events)                                |
+-----------------------------------------------------------------------------------------+
```

### Data Processing Pipeline
1. **Frame Capture**: Ingestion of raw uncompressed frames from offline video recordings (.mp4, .mov, .avi) or live UVC webcams.
2. **Optical Distortion Correction**: OpenCV camera matrix undistortion addressing radial and tangential wide-angle / fish-eye lens warp.
3. **Perspective Rectification**: Application of a static $3 \times 3$ Homography matrix $M$ converting skewed visual input into a normalized $1200 \times 700$ pixel top-down spatial representation.
4. **HSV Color Space Detection**: Dual-range thresholding in Hue, Saturation, and Value bounds, followed by morphological opening ($3 \times 3$ ellipse) and closing, with contour area and circularity metric filtering.
5. **Kalman Filter Estimation**: Integration of continuous physical state vectors $\mathbf{X}_k = [x, y, v_x, v_y]^T$ to smooth noisy visual detections and maintain trajectory prediction during rod and figure occlusions (up to 15 frames).
6. **Spatial Zone Mapping & Event Detection**: Canonical 8-bar field zone model and asynchronous FSM emitting discrete game events (Pass, Shot, Goal, Possession changes).
7. **Persistence & Analytics**: Asynchronous logging of structured event payloads to the SQLite persistence store, with live UI signal emissions for scores, speeds, and metrics.

---

## 2. Feature Prioritization (MoSCoW Matrix)

| Priority | ID | Feature Name | Description & Acceptance Criteria |
|---|---|---|---|
| **Must Have (P0)** | SYS-P0-01 | Dual Stream Ingestion | Support offline standard video files (.mov, .mp4, .avi) and live UVC camera feeds up to 1080p60. |
| **Must Have (P0)** | SYS-P0-02 | Interactive Calibration | 4-point UI selection utility mapping table playfield corners to a fixed $1200 \times 700$ top-down canvas. |
| **Must Have (P0)** | SYS-P0-03 | HSV Threshold Tuning | GUI utility with real-time visual mask previews for tuning color boundaries under changing ambient light. |
| **Must Have (P0)** | SYS-P0-04 | Core Centroid Ball Tracking | Extraction of ball position centroids, continuous coordinate output, and renderable motion trail overlay. |
| **Must Have (P0)** | SYS-P0-05 | Table Zone Partitioning | Logical breakdown of virtual table plane into 8 rod zones, 2 goal zones, and out-of-bounds boundary walls. |
| **Must Have (P0)** | SYS-P0-06 | Core Event State Machine | FSM detection for Goal, Ball Possession per bar, Shot Attempts, and 5-bar to 3-bar Pass Attempts and Successes. |
| **Must Have (P0)** | SYS-P0-07 | Relational Database Schema | SQLite storage modeling players, matches, match_players, and precise timestamped game_events. |
| **Must Have (P0)** | SYS-P0-08 | Live Match Dashboard | Main view presenting live scores, rod possession indicators, match clock, ball speed, and score override buttons. |
| **Must Have (P0)** | SYS-P0-09 | Match Summary View | End-of-match analytical report detailing goal breakdowns, shot volumes, pass completion rates, and possession split. |
| **Should Have (P1)** | SYS-P1-01 | Kalman Filter Tracking Engine | Linear Kalman filter sustaining continuous spatial state estimation across up to 15 contiguous occlusion frames. |
| **Should Have (P1)** | SYS-P1-02 | Ball Speed Calculation | Direct calculation and rendering of shot velocity in km/h derived from physical playfield spatial scale calibration. |
| **Should Have (P1)** | SYS-P1-03 | Advanced Shot Classification | Discrimination logic isolating genuine 3-bar shot attempts from defensive clearances originating from 2-bar or 5-bar. |
| **Should Have (P1)** | SYS-P1-04 | Defensive Save Detection | Spatial tracking identifying shots on target intercepted or deflected away from goal mouth vectors. |
| **Should Have (P1)** | SYS-P1-05 | Career Profile & Leaderboard | Historical aggregation dashboard showcasing player win/loss records, lifetime passing efficiency, and goal ratios. |
| **Should Have (P1)** | SYS-P1-06 | Configuration Persistence | Serialization of calibration matrices, camera indexes, and tuned HSV parameters to local `config.json`. |
| **Could Have (P2)** | SYS-P2-01 | Heatmap Generation | Spatial distribution rendering showing ball presence and shot origin density mapped onto top-down graphics. |
| **Could Have (P2)** | SYS-P2-02 | Optical Distortion Correction | OpenCV camera matrix calibration step addressing radial and tangential wide-angle / fish-eye lens warp. |
| **Could Have (P2)** | SYS-P2-03 | CSV / Summary Export | Automated compilation and export of match summaries into downloadable structured formats. |

---

## 3. Detailed Technical Implementation Guide

### Homography Transformation Module
Perspective distortion caused by off-center camera placement is resolved by computing a $3 \times 3$ transformation matrix $M$ using four non-collinear reference points selected from the physical table playfield corners:

$$\begin{bmatrix} x' \\ y' \\ 1 \end{bmatrix} \sim M \begin{bmatrix} x \\ y \\ 1 \end{bmatrix} = \begin{bmatrix} h_{11} & h_{12} & h_{13} \\ h_{21} & h_{22} & h_{23} \\ h_{31} & h_{32} & h_{33} \end{bmatrix} \begin{bmatrix} x \\ y \\ 1 \end{bmatrix}$$

- **Target Dimensions**: $1200 \times 700$ pixels.
- **Corner Mapping**: Clockwise order: Top-Left $(0,0)$, Top-Right $(1200,0)$, Bottom-Right $(1200,700)$, Bottom-Left $(0,700)$.

### Kalman Filter Formulation
- **State Vector**: $\mathbf{X}_k = [x_k, y_k, v_{x,k}, v_{y,k}]^T$
- **Measurement Vector**: $\mathbf{Z}_k = [x_{\text{meas}}, y_{\text{meas}}]^T$
- **State Transition Matrix**:
  $$F = \begin{bmatrix} 1 & 0 & \Delta t & 0 \\ 0 & 1 & 0 & \Delta t \\ 0 & 0 & 1 & 0 \\ 0 & 0 & 0 & 1 \end{bmatrix}$$
- **Measurement Matrix**:
  $$H = \begin{bmatrix} 1 & 0 & 0 & 0 \\ 0 & 1 & 0 & 0 \end{bmatrix}$$
- **Occlusion Handling**: When visual measurement is lost (ball obscured beneath player rods), the filter continues predicting state using $\mathbf{X}_{k|k-1} = F \mathbf{X}_{k-1}$ for up to 15 frames before declaring target lost.
