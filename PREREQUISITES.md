# StudyBuddyAvatar: pre-installation guide (fresh Windows machine)

Follow these steps in order on a new Windows laptop. Steps 1–6 are one-time installs; step 7 sets up the project.

## 0. What you need

| Item | Requirement |
|---|---|
| OS | Windows 10 (21H2+) or Windows 11, **64-bit** |
| Disk | ~6 GB free (Python env ~2 GB, speech model ~1 GB, CUDA PyTorch adds ~2.5 GB) |
| Hardware | Webcam and microphone (built-in is fine). An NVIDIA GPU is optional. |
| Network | Internet for the first setup only. The app runs fully offline afterwards. |

## 1. Microsoft Visual C++ Redistributable (x64)

PyTorch and OpenCV need it. Without it you get `OSError: [WinError 126] ... c10.dll`.

- Download **"Visual C++ Redistributable for Visual Studio 2015–2022, x64"** from <https://aka.ms/vs/17/release/vc_redist.x64.exe> and install it.
- Or from a terminal: `winget install Microsoft.VCRedist.2015+.x64`

## 2. Miniconda (Python environment manager)

1. Download the **Miniconda Windows 64-bit installer** from <https://www.anaconda.com/download/success> (Miniconda section). Anaconda also works.
2. Install with **"Just Me"**, use the default location, and **leave "Add to PATH" unchecked** (recommended).
3. Open **Anaconda Prompt** from the Start menu once and run:
   ```
   conda init powershell
   conda config --add channels conda-forge
   conda config --remove channels defaults
   conda config --set channel_priority strict
   ```
   Then close it. The first line lets `setup.bat` and PowerShell find conda. The other three switch conda to the free, open-source **conda-forge** channel. Recent conda versions otherwise require you to accept Anaconda's Terms of Service for their default channels, and PyCharm fails with `CondaToSNonInteractiveError` (see Troubleshooting).

   > Simpler alternative: install **Miniforge** (<https://conda-forge.org/download/>) instead of Miniconda. It uses conda-forge by default, so you only need `conda init powershell`.

> No conda? `setup.bat` falls back to a plain `.venv` if Python 3.12, 3.13 or 3.14 from <https://www.python.org/downloads/windows/> is installed (tick **"Add python.exe to PATH"**), or via `winget install Python.Python.3.14`.

## 3. PyCharm

Install PyCharm from <https://www.jetbrains.com/pycharm/download/?section=windows>. The free tier is enough.

## 4. NVIDIA driver (optional, GPU only)

If the laptop has an NVIDIA GPU, install the latest **Game Ready / Studio driver** from <https://www.nvidia.com/Download/index.aspx>. You do **not** need the CUDA Toolkit: PyTorch ships its own CUDA runtime. `setup.bat` detects the GPU (with `nvidia-smi`) and installs the matching PyTorch build. Without a GPU everything runs on the CPU, which is fine for this small model.

## 5. Windows camera and microphone permissions

Open **Settings → Privacy & security**:
- **Camera**: turn on *Camera access*, *Let apps access your camera*, and **Let desktop apps access your camera**.
- **Microphone**: turn on the same three switches.

## 6. Text-to-speech voices

Windows includes SAPI voices (e.g. *Microsoft David / Zira*), so nothing is needed by default. To add more, go to **Settings → Time & language → Speech → Add voices**.

## 7. Project setup

1. Copy or extract the project to a folder **without special characters**, e.g. `C:\Projects\StudyBuddyAvatar`.
2. Double-click **`setup.bat`**. It:
   - creates the conda env **`studybuddy`** (Python 3.14), or a `.venv` if conda is absent
   - installs PyTorch (CUDA or CPU automatically) and `requirements.txt`
   - downloads the Vosk speech model (~1 GB) if `audio_model/` is incomplete
   - runs `check_setup.py` and prints the interpreter path for PyCharm

   Options: `setup.bat -Cpu` (force CPU PyTorch), `setup.bat -NoConda` (force .venv).
3. In **PyCharm**: *File → Open* the project folder, then *Settings → Project → Python Interpreter → Add Interpreter → Add Local Interpreter → Conda Environment → Use existing environment → `studybuddy`*.
   Do **not** choose *Create new environment* in PyCharm. `setup.bat` has already created the env with the right packages, and a PyCharm-created env would be empty.
4. Open `main.py` and press **Run**. If you create a run configuration by hand, set the **working directory to the project folder**.

Outside PyCharm, double-click **`run.bat`**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `running scripts is disabled on this system` | Use `setup.bat` (it bypasses the policy for that run only), not `setup.ps1` directly. |
| `WinError 126 ... c10.dll` / `fbgemm.dll` | Install the VC++ redistributable (step 1) and reboot. |
| PyCharm doesn't list `studybuddy` | Choose *Python interpreter path* and browse to `%USERPROFILE%\miniconda3\envs\studybuddy\python.exe`. |
| `CondaToSNonInteractiveError: Terms of Service have not been accepted` | conda is still using Anaconda's default channels. Run the three `conda config` commands from step 2, then in PyCharm pick *Use existing → studybuddy* instead of creating a new env. (Or accept the terms with the `conda tos accept ...` commands shown in the error; they're free for education and small organisations.) |
| `conda` not recognised in setup | Run `conda init powershell` from Anaconda Prompt (step 2), or install Miniconda in its default location. |
| `ERROR: audio_model missing!` / Vosk fails to load | Re-run `setup.bat`; it re-downloads the model. Behind a proxy, download `vosk-model-en-in-0.5.zip` from <https://alphacephei.com/vosk/models> manually and extract its contents into `audio_model\`. |
| `[Vision] Camera not accessible` | Check step 5, close other apps using the camera (Teams, Zoom), or change `CAMERA_INDEX` in `config.py`. |
| No reply after saying the wake word | Check the microphone permission (step 5) and the default input device in Windows Sound settings. The wake word is set by `WAKE_WORD` in `config.py`. |
| Silent text-to-speech | Make sure at least one voice is installed (step 6) and the default output device isn't muted. |

## Training a new vision model (optional)

The repository ships the trained `vision_model/weights/best.pt`, so training is **not** needed to run the app. Training images are not included (`dataset/` holds only labels). To retrain:
1. Put your images and labels in `Dataset_Full/images`, `Dataset_Full/labels`, and `Dataset_Full/classes.txt`.
2. `python DatasetTrainTestSplit.py` creates `dataset/` and `data.yaml`.
3. `python ActionDetector_Model_Train.py`, then copy `runs/detect/yolo26n_custom/weights/best.pt` to `vision_model/weights/`.
