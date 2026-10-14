# Gesture Volume Control

Control your computer's system volume with a thumb-and-index-finger pinch gesture,
detected live from your webcam. Built with **OpenCV** (video I/O + drawing) and
**MediaPipe Hands** (21-point hand landmark detection).

## How it works

1. **Capture** — OpenCV reads frames from the webcam.
2. **Detect** — MediaPipe Hands locates 21 landmarks per hand in each frame.
3. **Measure** — Euclidean pixel distance between the thumb tip (landmark 4)
   and index fingertip (landmark 8) is computed.
4. **Map** — That distance is linearly interpolated from a calibrated
   `[min_dist, max_dist]` pixel range to a `[0, 100]` volume percentage.
5. **Smooth** — Exponential smoothing avoids jittery volume jumps frame-to-frame.
6. **Apply** — The percentage is pushed to the OS:
   - **Windows** → `pycaw` (Core Audio API)
   - **macOS** → `osascript` (`set volume output volume`)
   - **Linux** → `amixer` (PulseAudio mixer)

## Setup

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Linux users:** make sure `amixer` is installed (`sudo apt install alsa-utils`).

## Run

```bash
python volume_control.py
```

- Pinch thumb and index finger **together** → volume goes down (0%).
- Spread them **apart** → volume goes up (100%).
- A green bar on-screen shows the current level in real time.
- Press **`q`** to quit.

## Calibration

If the gesture range feels off (too sensitive or not sensitive enough), tune
these two values near the top of `HandVolumeApp.__init__`:

```python
self.dist_min = 25    # pixel distance treated as 0% volume
self.dist_max = 200   # pixel distance treated as 100% volume
```

Increase `dist_max` if you have to stretch your fingers very far apart to hit
100%; decrease it if 100% triggers too easily.

## Extending this project

Good next steps if you want to build on it:
- Add more gestures (e.g., open palm = mute, fist = play/pause) using landmark
  patterns instead of just two points.
- Support both hands simultaneously for two independent controls.
- Log gesture events to a file for a simple usage-analytics feature.
- Swap the volume backend for a media player API (Spotify, VLC) to control
  playback instead of system volume.
- Package it as a background/tray app that starts on login.

## Troubleshooting

| Issue | Fix |
|---|---|
| `Could not open webcam` | Try `cam_index=1` (or higher) in `main()` — some laptops enumerate cameras differently. |
| No hand detected | Ensure good, even lighting and keep your hand fully in frame. |
| Volume doesn't change (Windows) | Confirm `pycaw` and `comtypes` installed correctly; check console for a `[warn]` message. |
| Volume doesn't change (Linux) | Confirm `amixer` works standalone: `amixer -D pulse sset Master 50%`. Your mixer name may differ (`Master` vs `PCM`). |
