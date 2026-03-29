# ============================================================================
# setup_comfyui.ps1 — ComfyUI AMD (DirectML) setup for J_Claw Production
#
# Installs ComfyUI to C:\ComfyUI and wires it up for the AMD RX 9070 XT.
# Run from an elevated PowerShell prompt:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\scripts\setup_comfyui.ps1
# ============================================================================

$ErrorActionPreference = "Stop"
$ROOT     = "C:\ComfyUI"
$MODELS   = "$ROOT\models"
$ANIMDIFF = "$MODELS\animatediff_models"
$SDXL_DIR = "$MODELS\checkpoints"

Write-Host "`n=== J_Claw ComfyUI Setup (AMD/DirectML) ===" -ForegroundColor Cyan

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

# ── 3. Install PyTorch with DirectML ─────────────────────────────────────────
Write-Host "[3/6] Installing torch + torch-directml..." -ForegroundColor Green
# torch-directml works with CPU-based torch on Windows AMD
& $PIP install --upgrade pip
& $PIP install torch torchvision torchaudio
& $PIP install torch-directml
& $PIP install -r "$ROOT\requirements.txt"

# ── 4. Install ComfyUI AMD manager + custom nodes ────────────────────────────
Write-Host "[4/6] Installing ComfyUI Manager..." -ForegroundColor Green
$CUSTOM_NODES = "$ROOT\custom_nodes"
New-Item -ItemType Directory -Force -Path $CUSTOM_NODES | Out-Null
if (-not (Test-Path "$CUSTOM_NODES\ComfyUI-Manager")) {
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git "$CUSTOM_NODES\ComfyUI-Manager"
    & $PIP install -r "$CUSTOM_NODES\ComfyUI-Manager\requirements.txt" --quiet
}
if (-not (Test-Path "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved")) {
    git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved"
    & $PIP install -r "$CUSTOM_NODES\ComfyUI-AnimateDiff-Evolved\requirements.txt" --quiet
}

# ── 5. Download models ────────────────────────────────────────────────────────
Write-Host "[5/6] Downloading models..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $SDXL_DIR   | Out-Null
New-Item -ItemType Directory -Force -Path $ANIMDIFF    | Out-Null

# animagine-xl-3.1 (SDXL base — ~6.5 GB)
$ANIMAGINE = "$SDXL_DIR\animagine-xl-3.1.safetensors"
if (Test-Path $ANIMAGINE) {
    Write-Host "  [SKIP] animagine-xl-3.1.safetensors already present" -ForegroundColor Yellow
} else {
    Write-Host "  Downloading animagine-xl-3.1.safetensors (~6.5 GB)..." -ForegroundColor Cyan
    $url = "https://huggingface.co/cagliostrolab/animagine-xl-3.1/resolve/main/animagine-xl-3.1.safetensors"
    Invoke-WebRequest -Uri $url -OutFile $ANIMAGINE -Headers @{"Authorization"="Bearer $env:HF_TOKEN"} -Resume
}

# AnimateDiff motion module (mm_sdxl_v10_beta.ckpt — ~1.7 GB)
$MOTIONMOD = "$ANIMDIFF\mm_sdxl_v10_beta.ckpt"
if (Test-Path $MOTIONMOD) {
    Write-Host "  [SKIP] mm_sdxl_v10_beta.ckpt already present" -ForegroundColor Yellow
} else {
    Write-Host "  Downloading mm_sdxl_v10_beta.ckpt (~1.7 GB)..." -ForegroundColor Cyan
    $url = "https://huggingface.co/guoyww/animatediff/resolve/main/mm_sdxl_v10_beta.ckpt"
    Invoke-WebRequest -Uri $url -OutFile $MOTIONMOD -Headers @{"Authorization"="Bearer $env:HF_TOKEN"} -Resume
}

# ── 6. Write run_amd_gpu.bat ──────────────────────────────────────────────────
Write-Host "[6/6] Writing run_amd_gpu.bat..." -ForegroundColor Green
$BAT = @"
@echo off
:: ComfyUI — AMD RX 9070 XT (DirectML)
:: J_Claw Production Division launcher
cd /d C:\ComfyUI
call venv\Scripts\activate.bat
python main.py --directml --listen 127.0.0.1 --port 8188 --output-directory C:\ComfyUI\output %*
"@
Set-Content -Path "$ROOT\run_amd_gpu.bat" -Value $BAT -Encoding ASCII

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host "Launch ComfyUI:  C:\ComfyUI\run_amd_gpu.bat" -ForegroundColor Cyan
Write-Host "Dashboard check: http://127.0.0.1:8188" -ForegroundColor Cyan
Write-Host ""
Write-Host "NOTE: animagine-xl-3.1 requires a HuggingFace token for download." -ForegroundColor Yellow
Write-Host "      Set env var: `$env:HF_TOKEN = 'hf_...' before running this script," -ForegroundColor Yellow
Write-Host "      or download manually from: https://huggingface.co/cagliostrolab/animagine-xl-3.1" -ForegroundColor Yellow
Write-Host "      and place at: C:\ComfyUI\models\checkpoints\animagine-xl-3.1.safetensors" -ForegroundColor Yellow
