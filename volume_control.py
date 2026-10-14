import sys
import platform
import math
import subprocess
import time

import cv2
import mediapipe as mp
import numpy as np


# --------------------------------------------------------------------------
# OS-specific volume backend
# --------------------------------------------------------------------------
class VolumeController:
    """Wraps platform-specific system volume APIs behind one simple interface."""

    def __init__(self):
        self.system = platform.system()
        self.backend = None
        self.min_vol = 0
        self.max_vol = 100

        if self.system == "Windows":
            self._init_windows()
        elif self.system == "Darwin":
            self.backend = "macos"
        elif self.system == "Linux":
            self.backend = "linux"
        else:
            self.backend = "none"
            print(f"[warn] Unsupported OS '{self.system}'. Volume changes will be simulated only.")

    def _init_windows(self):
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
            self.min_vol, self.max_vol = self.volume_interface.GetVolumeRange()[:2]
            self.backend = "windows"
        except Exception as e:
            print(f"[warn] pycaw not available ({e}). Falling back to simulated volume.")
            self.backend = "none"

    def set_volume_percent(self, percent: float):
        """percent: 0-100"""
        percent = max(0, min(100, percent))

        if self.backend == "windows":
            vol_db = np.interp(percent, [0, 100], [self.min_vol, self.max_vol])
            self.volume_interface.SetMasterVolumeLevel(vol_db, None)

        elif self.backend == "macos":
            subprocess.run(["osascript", "-e", f"set volume output volume {int(percent)}"],
                            check=False)

        elif self.backend == "linux":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{int(percent)}%"],
                            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # backend == "none" -> no-op, UI still shows the bar


# --------------------------------------------------------------------------
# Hand tracking + gesture logic
# --------------------------------------------------------------------------
class HandVolumeApp:
    THUMB_TIP = 4
    INDEX_TIP = 8

    def __init__(self, cam_index=0, smoothing=0.3):
        self.cap = cv2.VideoCapture(cam_index)
        if not self.cap.isOpened():
            raise RuntimeError("Could not open webcam. Try a different cam_index.")

        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
        )
        self.mp_draw = mp.solutions.drawing_utils

        self.volume_ctrl = VolumeController()

        # Calibration range (pixels) for pinch distance -> 0-100%.
        # Adjust these two if it feels too sensitive / not sensitive enough.
        self.dist_min = 25
        self.dist_max = 200

        self.smoothing = smoothing  # 0 = no smoothing, closer to 1 = more smoothing
        self.smoothed_percent = 0
        self.prev_time = 0

    def _distance(self, p1, p2):
        return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

    def _draw_ui(self, frame, percent, fps):
        h, w, _ = frame.shape

        # Volume bar
        bar_x, bar_y, bar_w, bar_h = 50, 100, 35, 250
        filled = int(np.interp(percent, [0, 100], [bar_y + bar_h, bar_y]))
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (255, 255, 255), 2)
        cv2.rectangle(frame, (bar_x, filled), (bar_x + bar_w, bar_y + bar_h), (0, 255, 0), cv2.FILLED)
        cv2.putText(frame, f'{int(percent)}%', (bar_x - 5, bar_y + bar_h + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

        # FPS + backend info
        cv2.putText(frame, f'FPS: {int(fps)}', (w - 150, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.putText(frame, f'Backend: {self.volume_ctrl.backend}', (w - 220, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, "Pinch thumb + index | 'q' to quit", (10, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

    def run(self):
        print(f"[info] Volume backend: {self.volume_ctrl.backend}")
        print("[info] Press 'q' in the video window to quit.")

        while True:
            success, frame = self.cap.read()
            if not success:
                print("[error] Failed to grab frame from webcam.")
                break

            frame = cv2.flip(frame, 1)  # mirror for natural interaction
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb)

            percent = self.smoothed_percent

            if results.multi_hand_landmarks:
                hand_landmarks = results.multi_hand_landmarks[0]
                self.mp_draw.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)

                h, w, _ = frame.shape
                lm = hand_landmarks.landmark
                thumb = (int(lm[self.THUMB_TIP].x * w), int(lm[self.THUMB_TIP].y * h))
                index = (int(lm[self.INDEX_TIP].x * w), int(lm[self.INDEX_TIP].y * h))

                cv2.circle(frame, thumb, 10, (255, 0, 255), cv2.FILLED)
                cv2.circle(frame, index, 10, (255, 0, 255), cv2.FILLED)
                cv2.line(frame, thumb, index, (255, 0, 255), 3)

                dist = self._distance(thumb, index)
                raw_percent = np.interp(dist, [self.dist_min, self.dist_max], [0, 100])

                # Exponential smoothing to avoid jittery volume jumps
                self.smoothed_percent = (
                    self.smoothing * self.smoothed_percent + (1 - self.smoothing) * raw_percent
                )
                percent = self.smoothed_percent

                self.volume_ctrl.set_volume_percent(percent)

            # FPS calc
            curr_time = time.time()
            fps = 1 / (curr_time - self.prev_time) if self.prev_time else 0
            self.prev_time = curr_time

            self._draw_ui(frame, percent, fps)
            cv2.imshow("Gesture Volume Control", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        self.cap.release()
        cv2.destroyAllWindows()


def main():
    try:
        app = HandVolumeApp(cam_index=0)
        app.run()
    except RuntimeError as e:
        print(f"[fatal] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
