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

## Building a dataset offline (no Teachable Machine / Label Studio needed)

Run these in PyCharm (right-click the file → **Run**) or from the project folder, in order:

1. `python capture_tool.py`: one card per class (Mobile, Reading, Sleeping). Hold **Hold to Record**, or hold key **1/2/3**, to save webcam frames into `captured/<Class>/`. **Upload…** adds existing photos. **+ Add a class** creates a new class.
2. `python label_tool.py`: drag to draw a box. Keys **1/2/3** pick the class (the default is the folder the image came from). **A/D** go to the previous/next image, **Del** deletes a box, **Ctrl+Z** undoes. **Pre-label with model** uses the current `best.pt` to suggest boxes. Labels save automatically to `Dataset_Full/images`, `Dataset_Full/labels` and `Dataset_Full/classes.txt`.
3. `python DatasetTrainTestSplit.py`: splits `Dataset_Full/` into `dataset/` and rewrites `data.yaml`.
4. `python ActionDetector_Model_Train.py`: trains. Then copy `runs/detect/<run>/weights/best.pt` to `vision_model/weights/best.pt`.

Capture folders, output paths and the record rate are set in `config.py` under *Dataset tools*.

### Checking the tools work

1. **Interpreter**: in PyCharm, *Settings → Project → Python Interpreter*, pick the `studybuddy` conda env (or the project `.venv`). Run `check_setup.py`: `PyQt6.QtCore`, `cv2` and the camera should all be OK.
2. **Capture**: run `capture_tool.py`. You should see the webcam preview. Then check:
   - Hold **Hold to Record** on *Mobile* for ~3 s. The count goes up and thumbnails appear.
   - Holding key **2** records *Reading*.
   - **Open folder** shows the `.jpg` files in `captured/Mobile/`.
   - The status bar shows the totals for each class.
   - No preview? Change the *Camera* number, or check *Windows Settings → Privacy & security → Camera*.
3. **Label**: run `label_tool.py`. Images are listed as `· Mobile/Mobile_....jpg`. Then check:
   - Drag to draw a box, drag it to move it, drag a corner to resize it, press **2** to change its class, and press **Ctrl+Z** to undo.
   - Press **D**. The previous row turns green with **✓**.
   - Close the tool and reopen it. The box is still there.
4. **Output files**: in `Dataset_Full/`:
   - `classes.txt` reads `Mobile`, `Reading`, `Sleeping` (one per line).
   - Each `labels/<name>.txt` has lines like `0 0.41 0.59 0.62 0.78`: the class id (0 = Mobile, 1 = Reading, 2 = Sleeping), then 4 numbers between 0 and 1.
   - Every label has an image with the same name in `images/`.
   - Labels of `Sleeping_...` images should start with `2`.
5. **Pre-label**: open an image where you are clearly holding your phone and press **P**. An orange *Mobile* box should appear. This needs `vision_model/weights/best.pt`.
6. **Split**: run `DatasetTrainTestSplit.py`. It should print `train: N images` / `val: M images` with no `Skipping (no label)` lines for images you labelled. `data.yaml` should still list the same 3 names.
7. **Quick training test**: set `epochs=1` in `ActionDetector_Model_Train.py` and run it. It should start training and list all 3 classes. Set it back to `100` afterwards.
8. **Duplicate file names** (only matters if you used *Open folder…*): run this in PowerShell in the project folder, with your own folder in place of `C:\path\to\opened_folder`. It checks the source folders only, not `Dataset_Full\images`, which holds copies on purpose. If it prints nothing, no names clash. Any name it lists is shared by images that would also share one label file.
   ```powershell
   Get-ChildItem captured,C:\path\to\opened_folder -Recurse -File | Group-Object Name | Where-Object Count -gt 1
   ```

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
| `capture_tool.py` | Offline Teachable Machine: webcam capture per class into `captured/<Class>/` |
| `label_tool.py` | Offline Label Studio: draw/label bounding boxes, saves YOLO labels into `Dataset_Full/` |
| `dataset_tools_common.py` | Helpers shared by the two dataset tools |
| `setup.ps1` / `setup.bat`, `run.bat`, `requirements.txt`, `environment.yml` | Installation and launch |
