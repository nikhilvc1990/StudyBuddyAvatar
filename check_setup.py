"""Quick health check for a StudyBuddyAvatar install. Run: python check_setup.py"""
import importlib
import sys

from config import VOSK_MODEL_PATH, YOLO_MODEL_PATH, YOLO_ONNX_PATH, CAMERA_INDEX, LLM_ENABLED, LLM_URL, LLM_MODEL

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
    try:
        import torch
    except OSError as e:
        if "4551" in str(e):
            raise RuntimeError("blocked by Windows Smart App Control - fine for running the app "
                               "(vision uses ONNX), needed only for training (see PREREQUISITES.md)")
        raise
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU only"
    return f"{torch.__version__} ({gpu})"


def vosk_model():
    import vosk
    vosk.SetLogLevel(-1)
    vosk.Model(VOSK_MODEL_PATH)
    return VOSK_MODEL_PATH


def onnx_model():
    from detection import OnnxDetector
    import numpy as np
    d = OnnxDetector()
    d.detect(np.zeros((480, 640, 3), np.uint8))
    return f"{d.device}, classes {d.labels}"


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


def local_llm():
    import time
    import requests
    if not LLM_ENABLED:
        return "disabled in config.py (built-in replies)"
    try:
        tags = requests.get(f"{LLM_URL}/api/tags", timeout=2).json()
    except requests.ConnectionError:
        raise RuntimeError("Ollama not running/installed - built-in replies will be used")
    names = {m.get("name") for m in tags.get("models", [])}
    if LLM_MODEL not in names and f"{LLM_MODEL}:latest" not in names:
        raise RuntimeError(f"model not pulled (ollama pull {LLM_MODEL}) - built-in replies will be used")
    start = time.time()
    r = requests.post(f"{LLM_URL}/api/chat", json={
        "model": LLM_MODEL, "stream": False, "think": False,
        "messages": [{"role": "user", "content": "In one short sentence, what is photosynthesis?"}],
        "options": {"num_predict": 60},
    }, timeout=180)
    r.raise_for_status()
    answer = r.json()["message"]["content"].strip()
    return f"{LLM_MODEL} answered in {time.time() - start:.1f}s: {answer[:70]}"


print(f"Python {sys.version.split()[0]} at {sys.executable}")
print("Packages:")
for mod in ("PyQt6.QtCore", "pyttsx3", "sounddevice", "vosk", "cv2", "numpy"):
    check(mod, version(mod) if mod != "PyQt6.QtCore" else lambda: __import__("PyQt6.QtCore").QtCore.PYQT_VERSION_STR)
check("onnxruntime", version("onnxruntime"))
print("Models:")
check("Vosk speech model", vosk_model)
check("YOLO vision model (ONNX, used by the app)", onnx_model)
print("Training tools (warnings only):")
torch_ok = True
try:
    print(f"  [OK]   torch - {torch_info()}")
except Exception as e:
    torch_ok = False
    print(f"  [WARN] torch - {e}")
if torch_ok:
    warn("ultralytics", version("ultralytics"))
    warn("YOLO vision model (.pt)", yolo_model)
else:
    print("  [SKIP] ultralytics / best.pt - need torch")
print("Devices (warnings only):")
warn("Text-to-speech", tts_voices)
warn("Microphone", microphone)
warn("Camera", camera)
warn("Local AI brain (optional)", local_llm)

print("\nAll required checks passed." if ok else "\nSome required checks FAILED.")
sys.exit(0 if ok else 1)
