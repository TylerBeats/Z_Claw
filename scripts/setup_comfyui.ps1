# ============================================================================
# setup_comfyui.ps1 — ComfyUI AMD setup for J_Claw Production
#
# Installs ComfyUI to C:\ComfyUI and wires it up for the AMD RX 9070 XT.
# Run from an elevated PowerShell prompt:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\setup_comfyui.ps1
#
# Model downloads use huggingface-cli — set your token first if needed:
#   $env:HF_TOKEN = "hf_..."
# ============================================================================

$ErrorActionPreference = "Stop"
$ROOT     = "C:\ComfyUI"
$MODELS   = "$ROOT\models"
$ANIMDIFF = "$MODELS\animatediff_models"
$SDXL_DIR = "$MODELS\checkpoints"

Write-Host "`n=== J_Claw ComfyUI Setup (AMD) ===" -ForegroundColor Cyan

# ── 1. Clone ComfyUI ──────────────────────────────────────────────────────────
if (Test-Path "$ROOT\main.py") {
    Write-Host "[SKIP] ComfyUI already cloned at $ROOT" -ForegroundColor Yellow
} else {
    Write-Host "[1/6] Cloning ComfyUI..." -ForegroundColor Green
    git clone https://github.com/comfyanonymous/ComfyUI.git $ROOT
}

# ── 2. Create venv ────────────────────────────────────────────────────────────
$VENV = "$ROOT\venv"
if (Test-Path "$VENV\Scripts\python.exe") {
    Write-Host "[SKIP] venv already exists" -ForegroundColor Yellow
} else {
    Write-Host "[2/6] Creating Python venv..." -ForegroundColor Green
    python -m venv $VENV
}

$PIP  = "$VENV\Scripts\pip.exe"
$PY   = "$VENV\Scripts\python.exe"
$HF   = "$VENV\Scripts\huggingface-cli.exe"

# ── 3. Install PyTorch + ComfyUI requirements ─────────────────────────────────
Write-Host "[3/6] Installing torch + ComfyUI requirements..." -ForegroundColor Green
& $PY -m pip install --upgrade pip --quiet
& $PIP install torch torchvision torchaudio --quiet
& $PIP install -r "$ROOT\requirements.txt" --quiet

# torch-directml does not yet have a Python 3.13 build.
# Try installing it; if it fails, ComfyUI will fall back to CPU mode.
Write-Host "  Attempting torch-directml (Python 3.13 may not be supported yet)..." -ForegroundColor Yellow
$tdml = & $PIP install torch-directml 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] torch-directml installed — GPU acceleration enabled" -ForegroundColor Green
} else {
    Write-Host "  [WARN] torch-directml unavailable for this Python version." -ForegroundColor Yellow
    Write-Host "         ComfyUI will run in CPU mode until a compatible build is released." -ForegroundColor Yellow
}

# ── 4. Install custom nodes ────────────────────────────────────────────────────
Write-Host "[4/6] Installing custom nodes..." -ForegroundColor Green
$CUSTOM_NODES = "$ROOT\custom_nodes"
New-Item -ItemType Directory -Force -Path $CUSTOM_NODES | Out-Null

if (-not (Test-Path "$CUSTOM_NODES\ComfyUI-Manager")) {
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git "$CUSTOM_NODES\ComfyUI-Manager"
    if (Test-Path "$CUSTOM_NODES\ComfyUI-Manager\requirements.txt") {
        & $PIP install -r "$CUSTOM_NODES\ComfyUI-Manager\requirements.txt" --quiet
    }
} else {
    Write-Host "  [SKIP] ComfyUI-Manager already present" -ForegroundColor Yellow
}

if (-not (Test-Path "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved")) {
    git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved"
    if (Test-Path "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved\requirements.txt") {
        & $PIP install -r "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved\requirements.txt" --quiet
    } else {
        Write-Host "  [INFO] AnimateDiff-Evolved has no requirements.txt — no extra deps needed" -ForegroundColor Cyan
    }
} else {
    Write-Host "  [SKIP] ComfyUI-AnimateDiff-Evolved already present" -ForegroundColor Yellow
}

# ── 5. Download models via huggingface-cli ────────────────────────────────────
Write-Host "[5/6] Downloading models..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $SDXL_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $ANIMDIFF  | Out-Null

# Set HF token if provided
if ($env:HF_TOKEN) {
    & $HF login --token $env:HF_TOKEN 2>&1 | Out-Null
}

# animagine-xl-3.1 (SDXL base — ~6.5 GB)
$ANIMAGINE = "$SDXL_DIR\animagine-xl-3.1.safetensors"
if (Test-Path $ANIMAGINE) {
    Write-Host "  [SKIP] animagine-xl-3.1.safetensors already present" -ForegroundColor Yellow
} else {
    Write-Host "  Downloading animagine-xl-3.1.safetensors (~6.5 GB)..." -ForegroundColor Cyan
    & $HF download cagliostrolab/animagine-xl-3.1 animagine-xl-3.1.safetensors --local-dir $SDXL_DIR
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [WARN] Download failed — download manually and place at:" -ForegroundColor Red
        Write-Host "         $ANIMAGINE" -ForegroundColor Red
        Write-Host "         From: https://huggingface.co/cagliostrolab/animagine-xl-3.1" -ForegroundColor Red
    }
}

# AnimateDiff motion module (mm_sdxl_v10_beta.ckpt — ~1.7 GB)
$MOTIONMOD = "$ANIMDIFF\mm_sdxl_v10_beta.ckpt"
if (Test-Path $MOTIONMOD) {
    Write-Host "  [SKIP] mm_sdxl_v10_beta.ckpt already present" -ForegroundColor Yellow
} else {
    Write-Host "  Downloading mm_sdxl_v10_beta.ckpt (~1.7 GB)..." -ForegroundColor Cyan
    & $HF download guoyww/animatediff mm_sdxl_v10_beta.ckpt --local-dir $ANIMDIFF
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [WARN] Download failed — download manually and place at:" -ForegroundColor Red
        Write-Host "         $MOTIONMOD" -ForegroundColor Red
        Write-Host "         From: https://huggingface.co/guoyww/animatediff" -ForegroundColor Red
    }
}

# ── 6. Write run_amd_gpu.bat ──────────────────────────────────────────────────
Write-Host "[6/6] Writing run_amd_gpu.bat..." -ForegroundColor Green

# Use --directml if torch-directml is available, else --cpu
$useDirectml = & $PY -c "import torch_directml; print('yes')" 2>&1
if ($useDirectml -match "yes") {
    $gpuFlag = "--directml"
    Write-Host "  GPU mode: DirectML (AMD)" -ForegroundColor Green
} else {
    $gpuFlag = "--cpu"
    Write-Host "  GPU mode: CPU fallback (torch-directml not available for Python 3.13 yet)" -ForegroundColor Yellow
}

$BAT = @"
@echo off
:: ComfyUI — AMD RX 9070 XT
:: J_Claw Production Division launcher
cd /d C:\ComfyUI
call venv\Scripts\activate.bat
python main.py $gpuFlag --listen 127.0.0.1 --port 8188 --output-directory C:\ComfyUI\output %*
"@
Set-Content -Path "$ROOT\run_amd_gpu.bat" -Value $BAT -Encoding ASCII

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host "Launch ComfyUI:  C:\ComfyUI\run_amd_gpu.bat" -ForegroundColor Cyan
Write-Host "Check status:    http://127.0.0.1:8188" -ForegroundColor Cyan
Write-Host ""
if ($gpuFlag -eq "--cpu") {
    Write-Host "NOTE: Running CPU mode. When torch-directml adds Python 3.13 support," -ForegroundColor Yellow
    Write-Host "      run: C:\ComfyUI\venv\Scripts\pip install torch-directml" -ForegroundColor Yellow
    Write-Host "      then re-run this script to update run_amd_gpu.bat to --directml" -ForegroundColor Yellow
}
