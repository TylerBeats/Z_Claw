"""
doc-update skill — Tier 2 LLM (Qwen2.5 14B) with Tier 1 7B fallback.
Weekly — generates an architecture overview doc from the current runtime source.
Output is saved to hot cache for J_Claw to review and optionally publish.
"""

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from runtime.config import SKILL_MODELS, MODEL_14B_HOST, MODEL_7B, OLLAMA_HOST, ROOT
from runtime.ollama_client import chat, is_available

log     = logging.getLogger(__name__)
MODEL   = SKILL_MODELS["doc-update"]
HOT_DIR = ROOT / "divisions" / "dev-automation" / "hot"

SCAN_DIRS = ["runtime"]


def _module_inventory() -> list[dict]:
    """Collect file paths, sizes, and module docstrings from source."""
    inventory = []
    for d in SCAN_DIRS:
        p = ROOT / d
        if not p.exists():
            continue
        for f in sorted(p.rglob("*.py")):
            if "__pycache__" in str(f):
                continue
            try:
                lines     = f.read_text(encoding="utf-8", errors="replace").splitlines()
                docstring = ""
                in_doc    = False
                for line in lines[:25]:
                    stripped = line.strip()
                    if stripped.startswith(('"""', "'''")):
                        if in_doc:
                            break
                        in_doc    = True
                        docstring = stripped.lstrip('"\'').strip()
                        continue
                    if in_doc:
                        if stripped.endswith(('"""', "'''")):
                            docstring += " " + stripped.rstrip('"\'').strip()
                            break
                        docstring += " " + stripped
                inventory.append({
                    "path":      str(f.relative_to(ROOT)),
                    "lines":     len(lines),
                    "docstring": docstring.strip()[:200],
                })
            except Exception:
                pass
    return inventory


def run() -> dict:
    HOT_DIR.mkdir(parents=True, exist_ok=True)

    inventory = _module_inventory()

    if is_available(MODEL, host=MODEL_14B_HOST):
        use_model, use_host = MODEL, MODEL_14B_HOST
    elif is_available(MODEL_7B, host=OLLAMA_HOST):
        use_model, use_host = MODEL_7B, OLLAMA_HOST
    else:
        return {
            "status":       "partial",
            "summary":      "No model available for doc generation.",
            "docs_updated": [],
            "model_used":   None,
        }

    module_text = "\n".join(
        f"  {item['path']} ({item['lines']} lines)"
        + (f": {item['docstring']}" if item["docstring"] else "")
        for item in inventory
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Dev Automation doc agent for J_Claw. "
                "Given this Python runtime module inventory, write a concise architecture "
                "overview (max 400 words, plain markdown) covering: "
                "1) purpose of the runtime, "
                "2) key module groups (tools, skills, orchestrators), "
                "3) data flow from skills → orchestrators → executive packets → J_Claw, "
                "4) Ollama model tiers. "
                "Be specific and technical."
            ),
        },
        {
            "role": "user",
            "content": f"Module inventory ({len(inventory)} files):\n{module_text}",
        },
    ]

    try:
        doc_content = chat(use_model, messages, host=use_host, temperature=0.3, max_tokens=700)

        today    = date.today().isoformat()
        doc_path = HOT_DIR / f"architecture-doc-{today}.md"
        doc_path.write_text(doc_content, encoding="utf-8")

        log.info("doc-update: wrote %s (%d chars)", doc_path.name, len(doc_content))
        return {
            "status":       "success",
            "summary":      f"Architecture doc generated ({len(doc_content)} chars).",
            "docs_updated": [str(doc_path.relative_to(ROOT))],
            "doc_preview":  doc_content[:400],
            "model_used":   use_model,
        }
    except Exception as e:
        log.error("doc-update LLM failed: %s", e)
        return {
            "status":       "failed",
            "summary":      f"Doc update failed: {e}",
            "docs_updated": [],
            "model_used":   use_model,
        }
