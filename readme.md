# Study Buddy Avatar

A desktop study companion for students. A small animated avatar sits on top of your screen. It:
- **watches** through the webcam (YOLO26) and reacts when you're *Sleeping*, on your *Mobile*, or *Reading*
- **listens** for the wake word **"david"** (offline Vosk speech recognition) and answers simple questions
- **talks** back with offline Windows text-to-speech

Everything runs locally; no internet is needed after setup.

## Quick start (Windows)

1. Install the prerequisites in **[PREREQUISITES.md](PREREQUISITES.md)** (VC++ runtime, Miniconda, PyCharm, camera and mic permissions).
2. Double-click **`setup.bat`**.
3. In PyCharm, select the **`studybuddy`** conda interpreter, open `main.py`, and press **Run**. Or double-click **`run.bat`**.

Drag the avatar to move it; double-click it to quit.

Requires Python 3.12–3.14 (setup uses **3.14**).

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Entry point: wires the UI, vision, voice and TTS together |
| `config.py` | All settings (wake word, camera index, thresholds, messages) |
| `avatar.py`, `bridge.py` | PyQt6 avatar window and thread-safe UI signals |
| `detection.py` | Webcam + YOLO detection thread (`python detection.py` runs a standalone preview) |
| `voice.py`, `brain.py` | Wake word / command recognition and canned replies |
| `tts.py` | Prioritised text-to-speech queue |
| `check_setup.py` | Environment health check |
| `audio_model/` | Vosk Indian-English model (`vosk-model-en-in-0.5`, downloaded by setup) |
| `vision_model/weights/best.pt` | Trained YOLO26 detector (classes: Mobile, Reading, Sleeping) |
| `DatasetTrainTestSplit.py`, `ActionDetector_Model_Train.py`, `data.yaml`, `yolo26n.pt` | Retraining the vision model (see PREREQUISITES.md) |
| `setup.ps1` / `setup.bat`, `run.bat`, `requirements.txt`, `environment.yml` | Installation and launch |
