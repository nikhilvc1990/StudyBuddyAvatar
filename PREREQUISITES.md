# StudyBuddyAvatar: pre-installation guide (fresh Windows machine)

Follow these steps in order on a new Windows laptop. Steps 1–6 are one-time installs; step 7 sets up the project.

## 0. What you need

| Item | Requirement |
|---|---|
| OS | Windows 10 (21H2+) or Windows 11, **64-bit** |
| Disk | ~6 GB free (Python env ~2 GB, speech model ~1 GB, CUDA PyTorch adds ~2.5 GB); +~4 GB for the optional local AI |
| Local AI (optional) | NVIDIA GPU with 6 GB+ VRAM, **or** 16 GB RAM. Without it, the avatar uses built-in replies. |
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

## 4b. Ollama: local AI brain (optional)

With a local LLM the avatar gives real answers ("explain photosynthesis", "help me plan my revision") instead of fixed replies. It runs fully offline on your laptop.

- **Skip this step** if the laptop has less than 6 GB of NVIDIA VRAM **and** less than 16 GB RAM. `setup.bat` also checks this and skips the AI step on weaker laptops. Everything else works the same, with built-in replies.
- Install it with `winget install Ollama.Ollama`, or download it from <https://ollama.com/download>. Ollama then runs in the background (llama icon in the system tray) and starts with Windows.
- `setup.bat` downloads the model set in `config.py` (`LLM_MODEL`, default `gemma4:e4b`, about 3–4 GB). To do it by hand:
  ```
  ollama pull gemma4:e4b
  ```
- If you'd rather setup installed Ollama for you: `setup.bat -InstallOllama`.

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

   Options: `setup.bat -Cpu` (force CPU PyTorch), `setup.bat -NoConda` (force .venv), `setup.bat -InstallOllama` (also install the local AI), `setup.bat -SkipLLM` (no local AI).
3. In **PyCharm**: *File → Open* the project folder, then *Settings → Project → Python Interpreter → Add Interpreter → Add Local Interpreter → Conda Environment → Use existing environment → `studybuddy`*.
   Do **not** choose *Create new environment* in PyCharm. `setup.bat` has already created the env with the right packages, and a PyCharm-created env would be empty.
4. Open `main.py` and press **Run**. If you create a run configuration by hand, set the **working directory to the project folder**.

Outside PyCharm, double-click **`run.bat`**.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `running scripts is disabled on this system` | Use `setup.bat` (it bypasses the policy for that run only), not `setup.ps1` directly. |
| `[WinError 4551] An Application Control policy has blocked this file ... c10.dll` (console shows `[Vision] Disabled`) | **Windows Smart App Control** is blocking PyTorch, which is needed for the camera detection. Voice and the AI still work. To fix it, open *Windows Security → App & browser control → Smart App Control settings* and choose **Off**. On some Windows versions it can't be turned back on without resetting Windows, so decide whether that's acceptable. |
| `WinError 126 ... c10.dll` / `fbgemm.dll` | Install the VC++ redistributable (step 1) and reboot. |
| PyCharm doesn't list `studybuddy` | Choose *Python interpreter path* and browse to `%USERPROFILE%\miniconda3\envs\studybuddy\python.exe`. |
| `CondaToSNonInteractiveError: Terms of Service have not been accepted` | conda is still using Anaconda's default channels. Run the three `conda config` commands from step 2, then in PyCharm pick *Use existing → studybuddy* instead of creating a new env. (Or accept the terms with the `conda tos accept ...` commands shown in the error; they're free for education and small organisations.) |
| `conda` not recognised in setup | Run `conda init powershell` from Anaconda Prompt (step 2), or install Miniconda in its default location. |
| `ERROR: audio_model missing!` / Vosk fails to load | Re-run `setup.bat`; it re-downloads the model. Behind a proxy, download `vosk-model-en-in-0.5.zip` from <https://alphacephei.com/vosk/models> manually and extract its contents into `audio_model\`. |
| Console says `[LLM] not available (Ollama is not running)` | Start **Ollama** from the Start menu (the tray icon should appear). The avatar picks it up again within a minute. Built-in replies are used meanwhile. |
| `[LLM] not available (model not pulled ...)` | Run the `ollama pull ...` command it shows, or re-run `setup.bat`. |
| `[LLM] not available (not enough memory ...)` | Use a smaller model: set `LLM_MODEL = "llama3.2:3b"` in `config.py` and `ollama pull llama3.2:3b`. Or set `LLM_ENABLED = False`. |
| First AI answer is slow | The model loads into memory on first use (10–30 s). After that answers start in ~1–2 s. It stays loaded for 30 min (`LLM_KEEP_ALIVE`). |
| `[Vision] Camera not accessible` | Check step 5, close other apps using the camera (Teams, Zoom), or change `CAMERA_INDEX` in `config.py`. |
| Avatar doesn't react to "david" | Check the first lines of the Run console: `[Voice] Microphone: <name>` must be a mic you're actually using, and there must be no `seems silent` warning. A Bluetooth headset that's connected but not worn is a common cause. Run `mic_test.py` to see the level and what is heard, then set `MIC_DEVICE` in `config.py` (e.g. `"Realtek"`). Say "david" clearly and pause briefly. |
| No reply after saying the wake word | Check the microphone permission (step 5) and the default input device in Windows Sound settings. The wake word is set by `WAKE_WORD` in `config.py`. |
| Silent text-to-speech | Make sure at least one voice is installed (step 6) and the default output device isn't muted. |

## Training a new vision model (optional)

The repository ships the trained `vision_model/weights/best.pt`, so training is **not** needed to run the app. Training images are not included (`dataset/` holds only labels). To retrain:
1. Put your images and labels in `Dataset_Full/images`, `Dataset_Full/labels`, and `Dataset_Full/classes.txt`.
2. `python DatasetTrainTestSplit.py` creates `dataset/` and `data.yaml`.
3. `python ActionDetector_Model_Train.py`, then copy `runs/detect/yolo26n_custom/weights/best.pt` to `vision_model/weights/`.
