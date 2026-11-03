import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Audio / Voice ----
SAMPLERATE = 16000          # Vosk requires 16 kHz
BLOCKSIZE = 8000            # ~0.5 s of audio per callback
WAKE_WORD = "david"
# Words the speech model sometimes hears instead of the wake word
WAKE_WORD_ALIASES = ["david", "dave", "davit", "davis", "davide", "devid"]
LISTEN_TIMEOUT = 10.0       # seconds to wait for a command after wake word
# Microphone: None = Windows default input, or part of the device name, e.g. "Realtek"
# or "Buds" (run mic_test.py to list the names), or the device number.
MIC_DEVICE = None
VOSK_MODEL_PATH = os.path.join(BASE_DIR, "audio_model")

# ---- Vision ----
YOLO_MODEL_PATH = os.path.join(BASE_DIR, "vision_model", "weights", "best.pt")
# Same model exported to ONNX: runs with ONNX Runtime (Microsoft-signed, no PyTorch
# needed, so it works with Windows Smart App Control on). Re-export after retraining.
YOLO_ONNX_PATH = os.path.join(BASE_DIR, "vision_model", "weights", "best.onnx")
VISION_BACKEND = "auto"     # "auto" = ONNX if available, else PyTorch; or "onnx" / "torch"
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

# ---- Local AI brain (Ollama) ----
# Used when Ollama is running and the model is pulled; otherwise the built-in
# replies in brain.py are used automatically. Set LLM_ENABLED = False to never use it.
LLM_ENABLED = True
LLM_URL = "http://127.0.0.1:11434"   # 127.0.0.1, not localhost: avoids a 2 s IPv6 delay on Windows
LLM_MODEL = "gemma4:e4b"      # alternatives: qwen3.5:4b, gemma3:4b, llama3.2:3b
LLM_TIMEOUT = 30              # seconds to wait for a reply before falling back
LLM_MAX_TOKENS = 200          # keeps spoken answers short
LLM_TEMPERATURE = 0.7
LLM_KEEP_ALIVE = "30m"        # how long Ollama keeps the model loaded in memory
LLM_HISTORY_TURNS = 6         # question/answer pairs remembered for follow-ups
LLM_RETRY_INTERVAL = 60       # seconds between re-checks after the LLM goes away
VISION_CONTEXT_MAX_AGE = 15   # camera states older than this are not shown to the LLM

LLM_SYSTEM_PROMPT = (
    "You are David, a friendly and encouraging study buddy for students, shown as a small "
    "avatar on their screen. Your replies are spoken aloud, so answer in one to three short, "
    "simple sentences of plain text: no markdown, lists, emoji, code or special symbols. "
    "If a topic needs a longer explanation, give the short version and offer to explain more. "
    "The student's words come from speech recognition, so they are lowercase without "
    "punctuation and may contain mistakes; guess the intended meaning sensibly. "
    "Gently steer the student back to studying if they get distracted."
)

# ---- Dataset tools (capture_tool.py, label_tool.py) ----
DATA_YAML_PATH = os.path.join(BASE_DIR, "data.yaml")          # class names + order
CAPTURE_DIR = os.path.join(BASE_DIR, "captured")              # captured/<Class>/*.jpg
DATASET_FULL_DIR = os.path.join(BASE_DIR, "Dataset_Full")     # input to DatasetTrainTestSplit.py
CAPTURE_FPS = 5               # frames saved per second while "Hold to Record" is pressed
CAPTURE_SIZE = (640, 480)     # requested webcam resolution
CAPTURE_DELAY = 0             # default countdown (seconds) before recording starts