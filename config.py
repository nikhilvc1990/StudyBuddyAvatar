import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Audio / Voice ----
SAMPLERATE = 16000          # Vosk requires 16 kHz
BLOCKSIZE = 8000            # ~0.5 s of audio per callback
WAKE_WORD = "david"
LISTEN_TIMEOUT = 10.0       # seconds to wait for a command after wake word
VOSK_MODEL_PATH = os.path.join(BASE_DIR, "audio_model")

# ---- Vision ----
YOLO_MODEL_PATH = os.path.join(BASE_DIR, "vision_model", "weights", "best.pt")
CAMERA_INDEX = 0            # 0 = default webcam; try 1, 2… for external cameras
CONFIDENCE_LIMIT = 0.4
PRED_INTERVAL = 0.5
STABLE_COUNT = 5
SPEECH_COOLDOWN = 25
VISION_PRIORITY = ["Sleeping", "Mobile", "Reading"]   # highest first
REPEATING_STATES = {"Sleeping", "Mobile"}
ALERT_STATES = {"Sleeping", "Mobile"}                 # avatar turns red

VISION_MESSAGES = {
    "Sleeping": "Hey! Wake up, don't fall asleep while studying!",
    "Mobile":   "Put down your phone and focus on your studies!",
    "Reading":  "Great job! Keep reading, you are doing well!",
}

# ---- TTS ----
TTS_TIMEOUT = 15.0
TTS_RATE = 165
VOICE_SUPPRESS_WINDOW = 4.0   # seconds after a voice chat when vision alerts are muted

# ---- Dataset tools (capture_tool.py, label_tool.py) ----
DATA_YAML_PATH = os.path.join(BASE_DIR, "data.yaml")          # class names + order
CAPTURE_DIR = os.path.join(BASE_DIR, "captured")              # captured/<Class>/*.jpg
DATASET_FULL_DIR = os.path.join(BASE_DIR, "Dataset_Full")     # input to DatasetTrainTestSplit.py
CAPTURE_FPS = 5               # frames saved per second while "Hold to Record" is pressed
CAPTURE_SIZE = (640, 480)     # requested webcam resolution
CAPTURE_DELAY = 0             # default countdown (seconds) before recording starts