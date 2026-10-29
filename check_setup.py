"""Quick health check for a StudyBuddyAvatar install. Run: python check_setup.py"""
import importlib
import sys

from config import VOSK_MODEL_PATH, YOLO_MODEL_PATH, CAMERA_INDEX

ok = True


def check(label, fn):
    global ok
    try:
        detail = fn()
        print(f"  [OK]   {label}" + (f" - {detail}" if detail else ""))
    except Exception as e:
        ok = False
        print(f"  [FAIL] {label} - {e}")


def warn(label, fn):
    try:
        detail = fn()
        print(f"  [OK]   {label}" + (f" - {detail}" if detail else ""))
    except Exception as e:
        print(f"  [WARN] {label} - {e}")


def version(mod):
    return lambda: getattr(importlib.import_module(mod), "__version__", "imported")


def torch_info():
    import torch
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU only"
    return f"{torch.__version__} ({gpu})"


def vosk_model():
    import vosk
    vosk.SetLogLevel(-1)
    vosk.Model(VOSK_MODEL_PATH)
    return VOSK_MODEL_PATH


def yolo_model():
    from ultralytics import YOLO
    return f"classes {YOLO(YOLO_MODEL_PATH).names}"


def tts_voices():
    import pyttsx3
    voices = pyttsx3.init().getProperty("voices")
    if not voices:
        raise RuntimeError("no SAPI voices installed")
    return f"{len(voices)} voice(s)"


def microphone():
    import sounddevice as sd
    return sd.query_devices(kind="input")["name"]


def camera():
    import cv2
    cap = cv2.VideoCapture(CAMERA_INDEX)
    try:
        if not cap.isOpened() or not cap.read()[0]:
            raise RuntimeError(f"camera {CAMERA_INDEX} not accessible (check Windows privacy settings)")
        return f"camera {CAMERA_INDEX}"
    finally:
        cap.release()


print(f"Python {sys.version.split()[0]} at {sys.executable}")
print("Packages:")
for mod in ("PyQt6.QtCore", "pyttsx3", "sounddevice", "vosk", "cv2", "ultralytics", "numpy"):
    check(mod, version(mod) if mod != "PyQt6.QtCore" else lambda: __import__("PyQt6.QtCore").QtCore.PYQT_VERSION_STR)
check("torch", torch_info)
print("Models:")
check("Vosk speech model", vosk_model)
check("YOLO vision model", yolo_model)
print("Devices (warnings only):")
warn("Text-to-speech", tts_voices)
warn("Microphone", microphone)
warn("Camera", camera)

print("\nAll required checks passed." if ok else "\nSome required checks FAILED.")
sys.exit(0 if ok else 1)
