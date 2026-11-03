import ast
import os
import time
import threading

import cv2
import numpy as np

# torch / ultralytics / onnxruntime are imported inside the detectors, so if
# they can't load (e.g. DLLs blocked by Windows Smart App Control) only vision
# is disabled, not the whole app.
from config import (
    YOLO_MODEL_PATH as DEFAULT_MODEL_PATH,
    YOLO_ONNX_PATH,
    VISION_BACKEND,
    CAMERA_INDEX,
    CONFIDENCE_LIMIT,
    PRED_INTERVAL,
    STABLE_COUNT,
    SPEECH_COOLDOWN as COOLDOWN,
    VISION_PRIORITY as PRIORITY,
    REPEATING_STATES,
)


def select_device():
    import torch
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
        from ultralytics import YOLO
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

    def boxes(self, frame):
        """All boxes as (x1, y1, x2, y2, class_id, confidence) in frame pixels (used by label_tool)."""
        r = self.model.predict(source=frame, conf=self.conf, device=self.device, verbose=False)[0].boxes
        return [(*map(float, xyxy), int(c), float(p)) for xyxy, c, p in
                zip(r.xyxy.cpu().numpy(), r.cls.cpu().numpy(), r.conf.cpu().numpy())]

    @staticmethod
    def pick_state(detected, priority=PRIORITY):
        """Return (state, confidence) for the highest-priority detected class."""
        for name in priority:
            if name in detected:
                return name, detected[name]
        return None, 0.0


class OnnxDetector(Detector):
    """Same model exported to ONNX, run with ONNX Runtime (no PyTorch needed)."""

    def __init__(self, model_path=YOLO_ONNX_PATH, conf=CONFIDENCE_LIMIT):
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX model not found: {model_path}")
        import onnxruntime as ort
        self.conf = conf
        # DirectML uses any GPU (NVIDIA/AMD/Intel); falls back to CPU
        providers = [p for p in ("DmlExecutionProvider", "CPUExecutionProvider")
                     if p in ort.get_available_providers()]
        self.session = ort.InferenceSession(model_path, providers=providers)
        meta = self.session.get_modelmeta().custom_metadata_map
        self.labels = ast.literal_eval(meta["names"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.in_h, self.in_w = inp.shape[2], inp.shape[3]   # 480 x 640 = webcam frames
        self.device = self.session.get_providers()[0].replace("ExecutionProvider", "")
        print(f"[Detector] ONNX Runtime ({self.device}) | Labels: {self.labels}")

    def _letterbox(self, frame):
        """Resize keeping aspect ratio and pad to the model's input size (as ultralytics does)."""
        h, w = frame.shape[:2]
        r = min(self.in_h / h, self.in_w / w)
        nw, nh = round(w * r), round(h * r)
        img = frame if (nw, nh) == (w, h) else cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        top, left = (self.in_h - nh) // 2, (self.in_w - nw) // 2
        img = cv2.copyMakeBorder(img, top, self.in_h - nh - top, left, self.in_w - nw - left,
                                 cv2.BORDER_CONSTANT, value=(114, 114, 114))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).transpose(2, 0, 1)
        self._pad = (r, left, top)
        return np.ascontiguousarray(img[None], dtype=np.float32) / 255.0

    def detect(self, frame):
        # output0: [1, 4 + classes, anchors]; only the best score per class is needed
        out = self.session.run(None, {self.input_name: self._letterbox(frame)})[0][0]
        best = out[4:].max(axis=1)
        return {self.labels[i]: float(c) for i, c in enumerate(best) if c >= self.conf}

    def boxes(self, frame, iou=0.7):
        out = self.session.run(None, {self.input_name: self._letterbox(frame)})[0][0].T
        cls, conf = out[:, 4:].argmax(axis=1), out[:, 4:].max(axis=1)
        keep = conf >= self.conf
        out, cls, conf = out[keep], cls[keep], conf[keep]
        r, left, top = self._pad
        result = []
        for c in np.unique(cls):            # per-class NMS, like ultralytics
            m = cls == c
            cx, cy, w, h = out[m, :4].T
            xywh = np.stack([(cx - w / 2 - left) / r, (cy - h / 2 - top) / r, w / r, h / r], axis=1)
            for i in np.array(cv2.dnn.NMSBoxes(xywh.tolist(), conf[m].tolist(), self.conf, iou)).flatten():
                x, y, bw, bh = xywh[i]
                result.append((float(x), float(y), float(x + bw), float(y + bh), int(c), float(conf[m][i])))
        return result


def make_detector(backend=VISION_BACKEND):
    """ONNX Runtime if possible (works under Smart App Control), else PyTorch."""
    if backend in ("auto", "onnx"):
        try:
            return OnnxDetector()
        except Exception as e:
            if backend == "onnx":
                raise
            print(f"[Vision] ONNX not usable ({e}) - trying PyTorch")
    return Detector()


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
        self.last_state = None
        self.last_state_at = 0.0

    def stop(self):
        self._stop_flag.set()

    def get_state(self):
        """Most recent detected class and how many seconds ago it was seen."""
        return self.last_state, time.time() - self.last_state_at

    def run(self):
        try:
            detector = make_detector()
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
                self.last_state, self.last_state_at = state, now
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