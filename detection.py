import os
import time
import threading

import cv2
import torch
from ultralytics import YOLO

from config import (
    YOLO_MODEL_PATH as DEFAULT_MODEL_PATH,
    CAMERA_INDEX,
    CONFIDENCE_LIMIT,
    PRED_INTERVAL,
    STABLE_COUNT,
    SPEECH_COOLDOWN as COOLDOWN,
    VISION_PRIORITY as PRIORITY,
    REPEATING_STATES,
)


def select_device():
    if torch.cuda.is_available():
        return 0
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class Detector:
    """Wraps the YOLO model. Turns a frame into {class_name: best_confidence}."""

    def __init__(self, model_path=DEFAULT_MODEL_PATH, conf=CONFIDENCE_LIMIT):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"YOLO model not found: {model_path}")
        self.conf = conf
        self.device = select_device()
        self.model = YOLO(model_path)
        self.labels = self.model.names
        print(f"[Detector] Device: {self.device} | Labels: {self.labels}")

    def detect(self, frame):
        results = self.model.predict(
            source=frame, conf=self.conf, device=self.device, verbose=False
        )
        boxes = results[0].boxes
        detected = {}
        if len(boxes) == 0:
            return detected
        for cls_id, conf in zip(boxes.cls.cpu().numpy(), boxes.conf.cpu().numpy()):
            name = self.labels[int(cls_id)]
            if name not in detected or conf > detected[name]:
                detected[name] = float(conf)
        return detected

    @staticmethod
    def pick_state(detected, priority=PRIORITY):
        """Return (state, confidence) for the highest-priority detected class."""
        for name in priority:
            if name in detected:
                return name, detected[name]
        return None, 0.0


class StateFilter:
    """Stability filter + cooldown logic. No camera, no model."""

    def __init__(self, stable_count=STABLE_COUNT, cooldown=COOLDOWN):
        self.stable_count_needed = stable_count
        self.cooldown = cooldown
        self.reset()

    def reset(self):
        self.stable_state = None
        self.stable_count = 0
        self.last_state = None
        self.last_alert_at = 0.0

    def reset_last_state(self):
        self.last_state = None

    def update(self, state):
        """Feed one detection. Returns True if an alert should fire now."""
        if state == self.stable_state:
            self.stable_count += 1
        else:
            self.stable_state = state
            self.stable_count = 1

        if self.stable_count < self.stable_count_needed:
            return False

        new_state = state != self.last_state
        cooldown_over = (time.time() - self.last_alert_at) > self.cooldown

        if state in REPEATING_STATES:
            return new_state or cooldown_over
        return new_state    # e.g. Reading: only once, no repeats

    def commit(self, state):
        """Call after an alert was actually delivered."""
        self.last_state = state
        self.last_alert_at = time.time()
        self.stable_count = 0
        self.stable_state = None


class VisionThread(threading.Thread):
    """
    Reads the webcam, runs detection, and calls on_alert(state, confidence)
    when a stable state should trigger. If on_alert returns False, the alert
    is treated as suppressed and retried on the next stable frame.
    """

    def __init__(self, on_alert, model_path=DEFAULT_MODEL_PATH,
                 camera_index=CAMERA_INDEX, pred_interval=PRED_INTERVAL, show_preview=False):
        super().__init__(daemon=True, name="Vision")
        self.on_alert = on_alert
        self.model_path = model_path
        self.camera_index = camera_index
        self.pred_interval = pred_interval
        self.show_preview = show_preview
        self.filter = StateFilter()
        self._stop_flag = threading.Event()

    def stop(self):
        self._stop_flag.set()

    def run(self):
        try:
            detector = Detector(self.model_path)
        except Exception as e:
            print(f"[Vision] Disabled: {e}")
            return

        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print("[Vision] Camera not accessible. Vision disabled.")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("[Vision] Camera ready.")

        last_infer = 0.0
        try:
            while not self._stop_flag.is_set():
                ret, frame = cap.read()      # always read to keep the buffer fresh
                if not ret:
                    time.sleep(0.05)
                    continue

                if self.show_preview:
                    cv2.imshow("Vision preview (q to quit)", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                now = time.time()
                if now - last_infer < self.pred_interval:
                    continue
                last_infer = now

                detected = detector.detect(frame)
                state, conf = detector.pick_state(detected)
                if state is None:
                    continue
                print(f"[Vision] Detected: {detected}")

                if self.filter.update(state):
                    result = self.on_alert(state, conf)
                    if result is not False:
                        self.filter.commit(state)
        finally:
            cap.release()
            if self.show_preview:
                cv2.destroyAllWindows()
            print("[Vision] Camera released.")


# ---------- Standalone test: python detection.py ----------
if __name__ == "__main__":
    def print_alert(state, conf):
        print(f">>> ALERT: {state} ({conf:.0%})")
        return True

    t = VisionThread(on_alert=print_alert, show_preview=True)
    t.start()
    try:
        while t.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        t.stop()