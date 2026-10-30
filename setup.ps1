<#
.SYNOPSIS
  One-time setup for StudyBuddyAvatar on Windows 10/11 x64.

.DESCRIPTION
  1. Creates a conda env "studybuddy" (Python 3.14) - or, if conda is not
     installed, a local .venv using the Python launcher (3.14 / 3.13 / 3.12).
  2. Installs PyTorch (CUDA build if an NVIDIA GPU is detected, else CPU).
  3. Installs requirements.txt.
  4. Downloads the Vosk speech model if audio_model/ is missing or only
     contains Git LFS placeholder files.
  5. Optional local AI brain: if the laptop has >= 6 GB NVIDIA VRAM or
     >= 16 GB RAM and Ollama is installed, pulls the LLM model from config.py.
     Otherwise skipped - the avatar then uses its built-in replies.
  6. Runs check_setup.py and prints the interpreter path for PyCharm.

  Safe to re-run: existing env and model are reused.

.EXAMPLE
  .\setup.ps1                # normal
  .\setup.ps1 -Cpu           # force CPU-only PyTorch
  .\setup.ps1 -NoConda       # use a plain .venv even if conda exists
  .\setup.ps1 -InstallOllama # also install Ollama (local LLM) with winget
  .\setup.ps1 -SkipLLM       # no local LLM; built-in replies only
#>
param(
    [switch]$Cpu,
    [switch]$NoConda,
    [switch]$SkipModel,
    [switch]$SkipLLM,          # don't set up the local AI brain at all
    [switch]$InstallOllama,    # install Ollama with winget if it's missing
    [switch]$ForceLLM,         # set up the LLM even if the hardware check fails
    [string]$EnvName = "studybuddy",
    [string]$PythonVersion = "3.14"
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

$VoskModelName = "vosk-model-en-in-0.5"
$VoskModelUrl  = "https://alphacephei.com/vosk/models/$VoskModelName.zip"
$TorchIndex    = "https://download.pytorch.org/whl"

# Local LLM is only set up on laptops that can run it comfortably
$LlmMinVramGB = 6      # NVIDIA GPU memory, or...
$LlmMinRamGB  = 15     # ...system RAM for CPU-only (a "16 GB" laptop reports ~15.3)

function Step($msg)  { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Info($msg)  { Write-Host "    $msg" }
function Fail($msg)  { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# Run a native command; fail the script if it returns non-zero.
function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Exe @Arguments
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($code -ne 0) { Fail "'$Exe $($Arguments -join ' ')' failed (exit $code)" }
}

# ---------------------------------------------------------------- 1. Python env
function Find-Conda {
    $cmd = Get-Command conda -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $roots = @(
        "$env:USERPROFILE\miniconda3", "$env:USERPROFILE\anaconda3",
        "$env:LOCALAPPDATA\miniconda3", "$env:LOCALAPPDATA\anaconda3",
        "$env:ProgramData\miniconda3", "$env:ProgramData\anaconda3"
    )
    foreach ($r in $roots) {
        $exe = Join-Path $r "Scripts\conda.exe"
        if (Test-Path $exe) { return $exe }
    }
    return $null
}

function Get-CondaEnvPython($conda, $name) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $json = & $conda env list --json 2>$null | Out-String
    $ErrorActionPreference = $old
    foreach ($p in (ConvertFrom-Json $json).envs) {
        if ((Split-Path $p -Leaf) -eq $name) { return (Join-Path $p "python.exe") }
    }
    return $null
}

$Python = $null
$conda = if ($NoConda) { $null } else { Find-Conda }

if ($conda) {
    Step "Using conda: $conda"
    $Python = Get-CondaEnvPython $conda $EnvName
    if ($Python -and (Test-Path $Python)) {
        Info "Env '$EnvName' already exists - reusing it."
    } else {
        Info "Creating env '$EnvName' with Python $PythonVersion (conda-forge)..."
        Invoke-Native $conda @("create", "-y", "-n", $EnvName, "--override-channels",
                               "-c", "conda-forge", "python=$PythonVersion", "pip")
        $Python = Get-CondaEnvPython $conda $EnvName
        if (-not $Python) { Fail "conda env '$EnvName' was not created." }
    }
} else {
    Step "conda not found - using a local .venv"
    $Python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    if (Test-Path $Python) {
        Info ".venv already exists - reusing it."
    } else {
        $py = Get-Command py -ErrorAction SilentlyContinue
        $found = $null
        if ($py) {
            $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
            foreach ($v in @("3.14", "3.13", "3.12")) {
                & py "-$v" -c "import sys" 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) { $found = $v; break }
            }
            $ErrorActionPreference = $old
        }
        if (-not $found) {
            Fail ("No Python 3.12-3.14 found. Install Miniconda (recommended, see PREREQUISITES.md) " +
                  "or Python 3.14 from python.org / 'winget install Python.Python.3.14', then re-run.")
        }
        Info "Creating .venv with Python $found..."
        Invoke-Native "py" @("-$found", "-m", "venv", (Join-Path $ProjectDir ".venv"))
    }
}

$ver = & $Python -c "import sys; print('%d.%d' % sys.version_info[:2])"
Info "Interpreter: $Python (Python $ver)"
Invoke-Native $Python @("-m", "pip", "install", "--upgrade", "pip", "--quiet")

# ---------------------------------------------------------------- 2. PyTorch
Step "Installing PyTorch"
$flavor = "cpu"
if (-not $Cpu) {
    $smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($smi) {
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $smiOut = & nvidia-smi 2>$null | Out-String
        $ErrorActionPreference = $old
        # Older drivers print "CUDA Version: 12.6", newer ones "CUDA UMD Version: 13.3"
        if ($smiOut -match "CUDA (?:UMD )?Version:\s*(\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            Info "NVIDIA driver supports CUDA $major.$minor"
            if ($major -gt 13 -or ($major -eq 13 -and $minor -ge 2)) { $flavor = "cu132" }
            elseif ($major -eq 13) { $flavor = "cu130" }
            elseif ($major -eq 12 -and $minor -ge 6) { $flavor = "cu126" }
            else { Info "Driver too old for current PyTorch CUDA builds - update it for GPU support." }
        } else {
            Info "Could not read the CUDA version from nvidia-smi - using the CPU build."
        }
    } else {
        Info "No NVIDIA GPU detected."
    }
}
Info "Using PyTorch build: $flavor"
$torchArgs = @("-m", "pip", "install", "torch", "torchvision", "--index-url", "$TorchIndex/$flavor")
# pip treats 2.15.0+cpu as satisfying "torch", so switch builds explicitly on re-runs
$old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$installed = & $Python -c "import torch; print(torch.__version__)" 2>$null
$ErrorActionPreference = $old
if ($installed -and $installed -notlike "*+$flavor") {
    Info "Replacing installed torch $installed with the $flavor build"
    $torchArgs += @("--force-reinstall", "--no-deps")
}
Invoke-Native $Python $torchArgs

# ---------------------------------------------------------------- 3. Requirements
Step "Installing requirements.txt"
Invoke-Native $Python @("-m", "pip", "install", "-r", (Join-Path $ProjectDir "requirements.txt"))

# ---------------------------------------------------------------- 4. Vosk model
function Test-VoskModel {
    foreach ($rel in @("am\final.mdl", "graph\HCLG.fst", "conf\model.conf")) {
        $f = Join-Path $ProjectDir "audio_model\$rel"
        if (-not (Test-Path $f)) { return $false }
        if ((Get-Item $f).Length -lt 1024) {
            $head = Get-Content $f -TotalCount 1 -ErrorAction SilentlyContinue
            if ($head -like "version https://git-lfs*") { return $false }   # LFS placeholder
        }
    }
    return $true
}

Step "Checking Vosk speech model"
if ($SkipModel) {
    Info "Skipped (-SkipModel)."
} elseif (Test-VoskModel) {
    Info "audio_model/ is complete."
} else {
    Info "audio_model/ is missing or contains Git LFS placeholders - downloading $VoskModelName (~1 GB)..."
    $tmp = Join-Path $env:TEMP "studybuddy_vosk"
    New-Item -ItemType Directory -Force $tmp | Out-Null
    $zip = Join-Path $tmp "$VoskModelName.zip"
    if (-not (Test-Path $zip)) {
        Invoke-Native "curl.exe" @("-L", "--fail", "-o", "$zip.part", $VoskModelUrl)
        Move-Item "$zip.part" $zip -Force
    }
    Info "Extracting..."
    $extract = Join-Path $tmp "extract"
    if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
    New-Item -ItemType Directory -Force $extract | Out-Null
    Invoke-Native "tar.exe" @("-xf", $zip, "-C", $extract)
    $src = Join-Path $extract $VoskModelName
    if (-not (Test-Path $src)) { Fail "Unexpected archive layout in $zip" }

    # The old folder holds only placeholders / a partial model, so it is replaced outright
    $dst = Join-Path $ProjectDir "audio_model"
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Move-Item $src $dst
    Remove-Item $tmp -Recurse -Force
    if (-not (Test-VoskModel)) { Fail "Vosk model still incomplete after download." }
    Info "Vosk model installed."
}

# ---------------------------------------------------------------- 5. Local LLM (optional)
# Never fails setup: without an LLM the avatar uses its built-in replies.
function Find-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $exe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    if (Test-Path $exe) { return $exe }
    return $null
}

function Test-OllamaServer {
    try { Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null; return $true }
    catch { return $false }
}

function Install-LocalLLM {
    $ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
    $vramGB = 0
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        $mib = & nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>$null | Select-Object -First 1
        $ErrorActionPreference = $old
        if ($mib -match "^\s*(\d+)") { $vramGB = [math]::Round([int]$Matches[1] / 1024, 1) }
    }
    Info "Found $ramGB GB RAM, $vramGB GB NVIDIA VRAM"
    if (-not $ForceLLM -and $vramGB -lt $LlmMinVramGB -and $ramGB -lt $LlmMinRamGB) {
        Info ("This laptop doesn't meet the local-AI requirements (needs $LlmMinVramGB GB VRAM " +
              "or $LlmMinRamGB GB RAM). StudyBuddy will use its built-in replies.")
        return
    }

    $ollama = Find-Ollama
    if (-not $ollama) {
        if (-not $InstallOllama) {
            Info "Ollama is not installed. To enable the AI brain, install it and re-run setup:"
            Info "    winget install Ollama.Ollama      (or setup.bat -InstallOllama)"
            Info "Until then StudyBuddy uses its built-in replies."
            return
        }
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Write-Host "    WARNING: winget not found - install Ollama from https://ollama.com/download" -ForegroundColor Yellow
            return
        }
        Info "Installing Ollama..."
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
        $ErrorActionPreference = $old
        $ollama = Find-Ollama
        if (-not $ollama) {
            Write-Host "    WARNING: Ollama install failed - StudyBuddy will use its built-in replies." -ForegroundColor Yellow
            return
        }
    }
    Info "Ollama: $ollama"

    if (-not (Test-OllamaServer)) {
        Info "Starting Ollama..."
        Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden
        for ($i = 0; $i -lt 20 -and -not (Test-OllamaServer); $i++) { Start-Sleep -Seconds 1 }
        if (-not (Test-OllamaServer)) {
            Write-Host "    WARNING: Ollama did not start - StudyBuddy will use its built-in replies." -ForegroundColor Yellow
            return
        }
    }

    $model = (& $Python -c "import config; print(config.LLM_MODEL)").Trim()
    Info "Pulling model $model (a few GB the first time)..."
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $ollama pull $model
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($code -ne 0) {
        Write-Host "    WARNING: could not pull $model - StudyBuddy will use its built-in replies." -ForegroundColor Yellow
        return
    }
    Info "Local AI brain ready ($model)."
}

Step "Local AI brain (Ollama)"
if ($SkipLLM) {
    Info "Skipped (-SkipLLM). StudyBuddy will use its built-in replies."
} else {
    try { Install-LocalLLM }
    catch { Write-Host "    WARNING: LLM setup failed ($_) - StudyBuddy will use its built-in replies." -ForegroundColor Yellow }
}

# ---------------------------------------------------------------- 6. Health check
Step "Running health check"
$old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
& $Python (Join-Path $ProjectDir "check_setup.py")
$checkCode = $LASTEXITCODE
$ErrorActionPreference = $old

Write-Host ""
if ($checkCode -eq 0) {
    Write-Host "Setup complete." -ForegroundColor Green
} else {
    Write-Host "Setup finished, but the health check reported problems (see above)." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "PyCharm interpreter (Settings > Project > Python Interpreter > Add Interpreter):"
if ($conda) {
    Write-Host "  Conda Environment > Use existing > $EnvName"
    Write-Host "  (or point it directly at: $Python)"
} else {
    Write-Host "  Virtualenv Environment > Existing > $Python"
}
Write-Host "Run the app: open main.py in PyCharm and press Run, or double-click run.bat"
exit $checkCode
