"""
Shared config loader for the OpenClaw Python runtime.
Loads .env and provides paths + Ollama model config.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent          # OpenClaw-Orchestrator/
STATE_DIR = ROOT / "state"
LOGS_DIR = ROOT / "logs"
DIVISIONS_DIR = ROOT / "divisions"
REPORTS_DIR = ROOT / "reports"

# ── Environment ───────────────────────────────────────────────────────────────
load_dotenv(ROOT / ".env")

ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Tier 1 models (3060 Ti, CUDA)
MODEL_7B        = os.getenv("MODEL_7B",        "qwen2.5:7b-instruct-q4_K_M")
MODEL_8B        = os.getenv("MODEL_8B",        "llama3.1:8b-instruct-q4_K_M")
MODEL_CODER_7B  = os.getenv("MODEL_CODER_7B",  "qwen2.5-coder:7b-instruct-q4_K_M")

# Tier 2 model (friend's 9070 XT, ROCm) — fallback to Tier 1 if unavailable
MODEL_CODER_14B = os.getenv("MODEL_CODER_14B", "qwen2.5-coder:14b-instruct-q4_K_M")
MODEL_14B_HOST  = os.getenv("MODEL_14B_HOST",  "http://localhost:11434")  # override in .env when friend's machine is live

# ── Division model routing ────────────────────────────────────────────────────
SKILL_MODELS = {
    # Tier 1 — 3060 Ti (generic chat)
    "hard-filter":       MODEL_7B,
    "funding-finder":    MODEL_7B,
    "trading-report":    MODEL_7B,
    "perf-correlation":  MODEL_7B,
    "burnout-monitor":   MODEL_7B,
    "market-scan":       MODEL_7B,
    "health-logger":     MODEL_8B,        # privacy — local only, no fallback
    # Tier 1 — 3060 Ti (code-specialized) — repo metadata + pattern analysis
    "repo-monitor":      MODEL_CODER_7B,  # was 14B — metadata analysis, not deep reasoning
    "refactor-scan":     MODEL_CODER_7B,  # was 14B — pattern recognition, 7B sufficient
    "security-scan":     MODEL_CODER_7B,  # was generic 7B — Coder variant better for vuln patterns
    # Tier 2 — friend's 9070 XT (code-specialized) — deep reasoning tasks only
    "debug-agent":       MODEL_CODER_14B, # root cause analysis needs 14B
    "doc-update":        MODEL_CODER_14B, # broad context synthesis across many files
    # Orchestrator synthesis — local, text aggregation not code analysis
    "dev-digest":        MODEL_8B,        # Llama 3.1 8B — best local prose synthesis
    # OP-Sec — Tier 1 (7B local); device-posture and breach-check are Tier 0 (no model)
    "threat-surface":    MODEL_CODER_7B,  # code/config analysis benefits from Coder variant
    "cred-audit":        MODEL_CODER_7B,  # credential pattern matching in code files
    "privacy-scan":      MODEL_7B,        # PII scanning — generic fine, not code-specific
}


def division_config(division: str) -> dict:
    path = DIVISIONS_DIR / division / "config.json"
    with open(path) as f:
        return json.load(f)


def packet_path(division: str, skill: str) -> Path:
    return DIVISIONS_DIR / division / "packets" / f"{skill}.json"


def ensure_dirs():
    """Create any missing runtime directories."""
    for d in [STATE_DIR, LOGS_DIR, REPORTS_DIR]:
        d.mkdir(exist_ok=True)
    for div in ["opportunity", "trading", "personal", "dev-automation", "op-sec"]:
        for sub in ["packets", "hot", "cold", "manifests"]:
            (DIVISIONS_DIR / div / sub).mkdir(parents=True, exist_ok=True)
