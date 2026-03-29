# setup_comfyui.ps1 - ComfyUI AMD setup for J_Claw Production
#
# Run from project root in an elevated PowerShell:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\setup_comfyui.ps1
#
# Set HF token before running if animagine-xl-3.1 requires auth:
#   $env:HF_TOKEN = "hf_..."

$ErrorActionPreference = "Stop"
$ROOT     = "C:\ComfyUI"
$MODELS   = "$ROOT\models"
$ANIMDIFF = "$MODELS\animatediff_models"
$SDXL_DIR = "$MODELS\checkpoints"

Write-Host ""
Write-Host "=== J_Claw ComfyUI Setup (AMD) ===" -ForegroundColor Cyan

# Step 1 - Clone ComfyUI
if (Test-Path "$ROOT\main.py") {
    Write-Host "[SKIP] ComfyUI already cloned at $ROOT" -ForegroundColor Yellow
} else {
    Write-Host "[1/6] Cloning ComfyUI..." -ForegroundColor Green
    git clone https://github.com/comfyanonymous/ComfyUI.git $ROOT
}

# Step 2 - Create venv
$VENV = "$ROOT\venv"
if (Test-Path "$VENV\Scripts\python.exe") {
    Write-Host "[SKIP] venv already exists" -ForegroundColor Yellow
} else {
    Write-Host "[2/6] Creating Python venv..." -ForegroundColor Green
    python -m venv $VENV
}

$PIP = "$VENV\Scripts\pip.exe"
$PY  = "$VENV\Scripts\python.exe"
$HF  = "$VENV\Scripts\huggingface-cli.exe"

# Step 3 - Install PyTorch + ComfyUI requirements
Write-Host "[3/6] Installing torch + ComfyUI requirements..." -ForegroundColor Green
& $PY -m pip install --upgrade pip --quiet
& $PIP install torch torchvision torchaudio --quiet
& $PIP install -r "$ROOT\requirements.txt" --quiet
& $PIP install "huggingface-hub[cli]" --quiet

Write-Host "  Attempting torch-directml (Python 3.13 may not be supported yet)..." -ForegroundColor Yellow
$savedPref = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $PIP install torch-directml 2>&1 | Out-Null
$directmlExit = $LASTEXITCODE
$ErrorActionPreference = $savedPref
if ($directmlExit -eq 0) {
    Write-Host "  [OK] torch-directml installed" -ForegroundColor Green
} else {
    Write-Host "  [WARN] torch-directml not available for this Python version - will use CPU mode" -ForegroundColor Yellow
}

# Step 4 - Custom nodes
Write-Host "[4/6] Installing custom nodes..." -ForegroundColor Green
$CUSTOM_NODES = "$ROOT\custom_nodes"
New-Item -ItemType Directory -Force -Path $CUSTOM_NODES | Out-Null

if (Test-Path "$CUSTOM_NODES\ComfyUI-Manager") {
    Write-Host "  [SKIP] ComfyUI-Manager already present" -ForegroundColor Yellow
} else {
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git "$CUSTOM_NODES\ComfyUI-Manager"
    if (Test-Path "$CUSTOM_NODES\ComfyUI-Manager\requirements.txt") {
        & $PIP install -r "$CUSTOM_NODES\ComfyUI-Manager\requirements.txt" --quiet
    }
}

if (Test-Path "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved") {
    Write-Host "  [SKIP] ComfyUI-AnimateDiff-Evolved already present" -ForegroundColor Yellow
} else {
    git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved"
    if (Test-Path "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved\requirements.txt") {
        & $PIP install -r "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved\requirements.txt" --quiet
    } else {
        Write-Host "  [INFO] AnimateDiff-Evolved has no requirements.txt - skipping" -ForegroundColor Cyan
    }
}

# Step 5 - Download models via huggingface-cli
Write-Host "[5/6] Downloading models..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $SDXL_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $ANIMDIFF  | Out-Null

if ($env:HF_TOKEN) {
    & $HF login --token $env:HF_TOKEN 2>&1 | Out-Null
}

$ANIMAGINE = "$SDXL_DIR\animagine-xl-3.1.safetensors"
if (Test-Path $ANIMAGINE) {
    Write-Host "  [SKIP] animagine-xl-3.1.safetensors already present" -ForegroundColor Yellow
} else {
    Write-Host "  Downloading animagine-xl-3.1.safetensors (~6.5 GB)..." -ForegroundColor Cyan
    & $HF download cagliostrolab/animagine-xl-3.1 animagine-xl-3.1.safetensors --local-dir $SDXL_DIR
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [WARN] Download failed. Get it from:" -ForegroundColor Red
        Write-Host "         https://huggingface.co/cagliostrolab/animagine-xl-3.1" -ForegroundColor Red
        Write-Host "         Place at: $ANIMAGINE" -ForegroundColor Red
    }
}

$MOTIONMOD = "$ANIMDIFF\mm_sdxl_v10_beta.ckpt"
if (Test-Path $MOTIONMOD) {
    Write-Host "  [SKIP] mm_sdxl_v10_beta.ckpt already present" -ForegroundColor Yellow
} else {
    Write-Host "  Downloading mm_sdxl_v10_beta.ckpt (~1.7 GB)..." -ForegroundColor Cyan
    & $HF download guoyww/animatediff mm_sdxl_v10_beta.ckpt --local-dir $ANIMDIFF
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [WARN] Download failed. Get it from:" -ForegroundColor Red
        Write-Host "         https://huggingface.co/guoyww/animatediff" -ForegroundColor Red
        Write-Host "         Place at: $MOTIONMOD" -ForegroundColor Red
    }
}

# Step 6 - Write run_amd_gpu.bat
Write-Host "[6/6] Writing run_amd_gpu.bat..." -ForegroundColor Green

$hasDirectml = & $PY -c "import torch_directml; print('yes')" 2>&1
if ($hasDirectml -match "yes") {
    $gpuFlag = "--directml"
    Write-Host "  GPU mode: DirectML" -ForegroundColor Green
} else {
    $gpuFlag = "--cpu"
    Write-Host "  GPU mode: CPU (torch-directml unavailable for Python 3.13)" -ForegroundColor Yellow
}

$batContent = "@echo off" + [Environment]::NewLine
$batContent += ":: ComfyUI - AMD RX 9070 XT" + [Environment]::NewLine
$batContent += ":: J_Claw Production Division launcher" + [Environment]::NewLine
$batContent += "cd /d C:\ComfyUI" + [Environment]::NewLine
$batContent += "call venv\Scripts\activate.bat" + [Environment]::NewLine
$batContent += "python main.py $gpuFlag --listen 127.0.0.1 --port 8188 --output-directory C:\ComfyUI\output %*" + [Environment]::NewLine
[System.IO.File]::WriteAllText("$ROOT\run_amd_gpu.bat", $batContent, [System.Text.Encoding]::ASCII)

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host "Launch ComfyUI:  C:\ComfyUI\run_amd_gpu.bat" -ForegroundColor Cyan
Write-Host "Check UI:        http://127.0.0.1:8188" -ForegroundColor Cyan
if ($gpuFlag -eq "--cpu") {
    Write-Host ""
    Write-Host "NOTE: CPU mode active. Once torch-directml supports Python 3.13," -ForegroundColor Yellow
    Write-Host "      run: C:\ComfyUI\venv\Scripts\pip install torch-directml" -ForegroundColor Yellow
    Write-Host "      then re-run this script to switch run_amd_gpu.bat to --directml" -ForegroundColor Yellow
}
