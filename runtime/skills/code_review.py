"""
Code Reviewer — static analysis and best-practice review via LLM.

Uses Qwen2.5-Coder 14B (Tier 2) with 7B coder fallback.
Reads code from parameter or from state/gamedev/code/.
Output saved to divisions/gamedev/reviews/.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import (
    MODEL_CODER_14B, MODEL_CODER_7B,
    MODEL_14B_HOST, OLLAMA_HOST, BASE_DIR,
)
from runtime.ollama_client import chat_json, is_available

log = logging.getLogger(__name__)

CODE_STATE_DIR = BASE_DIR / "state" / "gamedev" / "code"
OUTPUT_DIR     = BASE_DIR / "divisions" / "gamedev" / "reviews"

_SYSTEM_PROMPT_TEMPLATE = """\
You are a senior code reviewer for J_Claw's game development division.
Review the provided {engine} code for bugs, architecture issues, best practices, and security problems.
Return ONLY valid JSON:
{{
  "verdict": "pass | fail | review",
  "summary": "one-sentence overall assessment",
  "issues": [
    {{
      "severity": "critical | major | minor",
      "line_hint": "approximate line or function name (string)",
      "description": "what the issue is",
      "suggestion": "how to fix it"
    }}
  ],
  "suggestions": ["general improvement suggestions (strings)"],
  "security_notes": ["security observations, empty list if none"],
  "architecture_notes": "brief architecture assessment"
}}
Be thorough. Flag every real issue. Do not invent problems that aren't there.\
"""


def _load_code_from_state() -> tuple[str, str]:
    """Return (code, filename) of the most recently modified file in state/gamedev/code/."""
    if not CODE_STATE_DIR.exists():
        return "", ""
    candidates = sorted(
        (f for f in CODE_STATE_DIR.iterdir() if f.is_file()),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return "", ""
    target = candidates[0]
    return target.read_text(encoding="utf-8", errors="replace"), target.name


def run(code: str = "", filename: str = "", engine: str = "godot") -> dict:
    """Code Review skill entry point."""

    # Resolve code source
    if not code:
        code, filename = _load_code_from_state()
        if not code:
            return {
                "status": "failed",
                "summary": "No code provided and no files found in state/gamedev/code/.",
                "metrics": {}, "action_items": [], "escalate": False,
            }

    lines_reviewed = len(code.splitlines())

    # Model selection
    if is_available(MODEL_CODER_14B, host=MODEL_14B_HOST):
        use_model, use_host, tier = MODEL_CODER_14B, MODEL_14B_HOST, "coder_14b"
    elif is_available(MODEL_CODER_7B, host=OLLAMA_HOST):
        log.info("code_review: 14B unavailable, falling back to coder 7B")
        use_model, use_host, tier = MODEL_CODER_7B, OLLAMA_HOST, "coder_7b_fallback"
    else:
        return {
            "status": "partial",
            "summary": f"Code review queued for '{filename}'. No coder model available.",
            "metrics": {"filename": filename, "lines_reviewed": lines_reviewed},
            "action_items": [
                {"priority": "medium",
                 "description": "Start Ollama with a coder model to run code review.",
                 "requires_matthew": False}
            ],
            "escalate": False,
        }

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(engine=engine)
    user_content = f"Filename: {filename or 'unnamed'}\nEngine: {engine}\n\n```\n{code}\n```"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_content},
    ]

    try:
        result = chat_json(use_model, messages, host=use_host, temperature=0.1, max_tokens=3000)
        if not isinstance(result, dict):
            raise ValueError(f"Unexpected LLM response type: {type(result)}")

        issues       = result.get("issues", [])
        verdict      = result.get("verdict", "review")
        summary      = result.get("summary", "Review complete.")
        suggestions  = result.get("suggestions", [])
        issue_count  = len(issues)
        critical_count = sum(1 for i in issues if i.get("severity") == "critical")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = (filename or "unnamed").replace("/", "_").replace("\\", "_")
        out_path  = OUTPUT_DIR / f"{timestamp}_review_{safe_name}.json"
        out_path.write_text(
            json.dumps({
                "filename": filename,
                "engine": engine,
                "model_tier": tier,
                "lines_reviewed": lines_reviewed,
                **result,
            }, indent=2),
            encoding="utf-8",
        )

        log.info(
            "code_review: %s — verdict=%s issues=%d critical=%d (%s)",
            filename, verdict, issue_count, critical_count, tier,
        )

        action_items = []
        for issue in issues:
            if issue.get("severity") in ("critical", "major"):
                action_items.append({
                    "priority": "high" if issue["severity"] == "critical" else "medium",
                    "description": f"[{issue['severity'].upper()}] {issue.get('description', '')}",
                    "requires_matthew": issue["severity"] == "critical",
                })

        return {
            "status":  "success",
            "summary": (
                f"Review of '{filename}': {verdict.upper()}. "
                f"{issue_count} issue(s) found ({critical_count} critical). "
                f"{summary}"
            ),
            "metrics": {
                "filename":      filename,
                "engine":        engine,
                "verdict":       verdict,
                "issue_count":   issue_count,
                "critical_count": critical_count,
                "lines_reviewed": lines_reviewed,
                "model_tier":    tier,
                "output_path":   str(out_path.relative_to(BASE_DIR)),
            },
            "action_items": action_items,
            "escalate": critical_count > 0,
        }

    except Exception as exc:
        log.error("code_review: LLM call failed — %s", exc)
        return {
            "status":  "failed",
            "summary": f"Code review failed: {exc}",
            "metrics": {"filename": filename, "engine": engine, "lines_reviewed": lines_reviewed},
            "action_items": [], "escalate": False,
        }
