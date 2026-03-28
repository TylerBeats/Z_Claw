"""
Video Generator — generates short animated clips via ComfyUI + AnimateDiff.

Uses the AnimateDiff-Evolved custom node for ComfyUI (SDXL pipeline) when
ComfyUI is running at http://127.0.0.1:8188.  Falls back to queue-only mode
if ComfyUI is offline or AnimateDiff nodes are not installed.

AMD/Windows notes
-----------------
* ComfyUI already handles DirectML / RDNA 4 — no extra config needed here.
* AnimateDiff motion module: mm_sdxl_v10_beta.ckpt
  Place in: ComfyUI/models/animatediff_models/
* Checkpoint: animagine-xl-3.1.safetensors (already used for images)

ComfyUI custom node required:
    cd ComfyUI/custom_nodes
    git clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved
    (restart ComfyUI after installing)
"""

import json
import logging
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from runtime.config import BASE_DIR

log = logging.getLogger(__name__)

COMFYUI_URL  = "http://127.0.0.1:8188"
QUEUE_FILE   = BASE_DIR / "state" / "video-queue.json"
VIDEO_OUT    = BASE_DIR / "mobile" / "assets" / "generated" / "videos"

MOTION_MODULE = "mm_sdxl_v10_beta.ckpt"
CHECKPOINT    = "animagine-xl-3.1.safetensors"
FRAMES        = 16
FPS           = 8


# ---------------------------------------------------------------------------
# ComfyUI helpers
# ---------------------------------------------------------------------------

def _comfyui_available() -> bool:
    try:
        urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=3)
        return True
    except Exception:
        return False


def _build_animatediff_workflow(positive: str, negative: str, commander: str, scene_type: str, client_id: str) -> dict:
    """Build an AnimateDiff-Evolved ComfyUI API workflow for SDXL."""
    seed = int(time.time()) % 2**32
    return {
        "client_id": client_id,
        "prompt": {
            "loader": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": CHECKPOINT},
            },
            "animatediff_loader": {
                "class_type": "ADE_AnimateDiffLoaderWithContext",
                "inputs": {
                    "model":         ["loader", 0],
                    "model_name":    MOTION_MODULE,
                    "beta_schedule": "sqrt_linear (AnimateDiff)",
                },
            },
            "positive_prompt": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["loader", 1], "text": positive},
            },
            "negative_prompt": {
                "class_type": "CLIPTextEncode",
                "inputs": {"clip": ["loader", 1], "text": negative},
            },
            "latent": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 768, "height": 512, "batch_size": FRAMES},
            },
            "sampler": {
                "class_type": "KSampler",
                "inputs": {
                    "model":        ["animatediff_loader", 0],
                    "positive":     ["positive_prompt", 0],
                    "negative":     ["negative_prompt", 0],
                    "latent_image": ["latent", 0],
                    "seed":         seed,
                    "steps":        20,
                    "cfg":          7.0,
                    "sampler_name": "euler_ancestral",
                    "scheduler":    "karras",
                    "denoise":      1.0,
                },
            },
            "decode": {
                "class_type": "VAEDecode",
                "inputs": {"samples": ["sampler", 0], "vae": ["loader", 2]},
            },
            "save": {
                "class_type": "SaveAnimatedWEBP",
                "inputs": {
                    "images":          ["decode", 0],
                    "filename_prefix": f"vid_{commander}_{scene_type}",
                    "fps":             FPS,
                    "lossless":        False,
                    "quality":         85,
                    "method":          "default",
                },
            },
        },
    }


def _submit_and_wait(workflow: dict, timeout_s: int = 600) -> dict:
    data = json.dumps(workflow).encode("utf-8")
    req  = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read())
    prompt_id = result.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI rejected prompt: {result}")

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(5)
        try:
            with urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5) as r:
                history = json.loads(r.read())
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                files = []
                for node_out in outputs.values():
                    for item in node_out.get("gifs", []):
                        files.append(item["filename"])
                    for item in node_out.get("images", []):
                        if item["filename"].endswith(".webp"):
                            files.append(item["filename"])
                return {"prompt_id": prompt_id, "files": files}
        except Exception:
            pass

    raise TimeoutError(f"ComfyUI video generation timed out after {timeout_s}s")


def _copy_output(filename: str, commander: str) -> str | None:
    """Download a ComfyUI output file via the /view endpoint."""
    try:
        out_dir = VIDEO_OUT / commander
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / filename
        urllib.request.urlretrieve(f"{COMFYUI_URL}/view?filename={filename}&type=output", str(dest))
        return str(dest.relative_to(BASE_DIR)).replace("\\", "/")
    except Exception as exc:
        log.warning("video_generate: could not copy %s — %s", filename, exc)
        return None


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------

def _load_queue() -> list:
    if not QUEUE_FILE.exists():
        return []
    try:
        with open(QUEUE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_queue(queue: list) -> None:
    QUEUE_FILE.parent.mkdir(exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------

_COMMANDER_PROMPTS = {
    "vael":    "tactical commander, dark armor, golden accents, determined expression",
    "seren":   "calculating strategist, silver and blue robes, calm demeanor",
    "kaelen":  "forge master, heavy plate armor, glowing runes, intense focus",
    "lyrin":   "healer commander, warm ember glow, flowing robes, compassionate",
    "zeth":    "shadow operative, dark cloak, minimal silhouette, covert stance",
    "lyke":    "craftsperson commander, workshop setting, tools and blueprints",
    "generic": "armored commander, fantasy battle scene",
}

_SCENE_PROMPTS = {
    "battle":  "dramatic battle scene, dynamic action, cinematic lighting",
    "victory": "triumphant victory pose, golden light, celebration",
    "idle":    "idle standing pose, ambient environment, subtle movement",
    "ability": "special ability activation, magical energy, particle effects",
    "defeat":  "defeated pose, dark atmosphere, somber lighting",
}

_NEGATIVE = (
    "ugly, deformed, disfigured, blurry, low quality, watermark, text, "
    "signature, bad anatomy, extra limbs"
)


def _build_prompts(scene_type: str, commander: str, description: str) -> tuple[str, str]:
    cmdr_desc  = _COMMANDER_PROMPTS.get(commander, _COMMANDER_PROMPTS["generic"])
    scene_desc = _SCENE_PROMPTS.get(scene_type, _SCENE_PROMPTS["battle"])
    custom     = f", {description}" if description else ""
    return f"masterpiece, best quality, {cmdr_desc}, {scene_desc}{custom}, animated", _NEGATIVE


# ---------------------------------------------------------------------------
# Skill entry point
# ---------------------------------------------------------------------------

def run(
    scene_type:  str = "battle",
    commander:   str = "generic",
    description: str = "",
) -> dict:
    """
    Video Generator skill entry point.

    When ComfyUI + AnimateDiff-Evolved are running: generates a 16-frame
    animated WEBP and saves it to mobile/assets/generated/videos/{commander}/.
    When ComfyUI is offline: queues the request for later processing.
    """
    queue = _load_queue()
    entry = {
        "id":          f"vid-{len(queue)+1:04d}",
        "scene_type":  scene_type,
        "commander":   commander,
        "description": description or f"{commander} {scene_type} scene",
        "status":      "queued",
        "queued_at":   datetime.now(timezone.utc).isoformat(),
    }
    queue.append(entry)

    if not _comfyui_available():
        _save_queue(queue)
        log.info("video_generate: ComfyUI offline — queued %s", entry["id"])
        return {
            "status":  "partial",
            "summary": (
                f"Video request queued ({entry['id']}). ComfyUI is offline. "
                "Start ComfyUI with AnimateDiff-Evolved installed, then retry."
            ),
            "metrics": {
                "queue_id":    entry["id"],
                "scene_type":  scene_type,
                "commander":   commander,
                "queue_depth": len(queue),
            },
            "action_items": [{
                "priority":         "medium",
                "description":      (
                    "Start ComfyUI and ensure AnimateDiff-Evolved is installed. "
                    "Motion module mm_sdxl_v10_beta.ckpt belongs in ComfyUI/models/animatediff_models/"
                ),
                "requires_matthew": True,
            }],
            "escalate": False,
        }

    try:
        positive, negative = _build_prompts(scene_type, commander, description)
        client_id = str(uuid.uuid4())
        workflow  = _build_animatediff_workflow(positive, negative, commander, scene_type, client_id)

        log.info("video_generate: submitting AnimateDiff job %s (%s/%s)", entry["id"], commander, scene_type)
        result = _submit_and_wait(workflow, timeout_s=600)

        saved_paths = [p for p in (_copy_output(f, commander) for f in result.get("files", [])) if p]

        if saved_paths:
            entry["status"]       = "completed"
            entry["output_paths"] = saved_paths
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
            _save_queue(queue)
            return {
                "status":  "success",
                "summary": f"Video generated ({entry['id']}): {commander}/{scene_type}, {len(saved_paths)} file(s).",
                "metrics": {
                    "queue_id":    entry["id"],
                    "scene_type":  scene_type,
                    "commander":   commander,
                    "video_paths": saved_paths,
                    "frames":      FRAMES,
                    "fps":         FPS,
                    "queue_depth": len(queue),
                },
                "action_items": [],
                "escalate": False,
            }
        else:
            entry["status"]    = "failed"
            entry["failed_at"] = datetime.now(timezone.utc).isoformat()
            _save_queue(queue)
            return {
                "status":  "failed",
                "summary": f"Video generation completed but no output files found ({entry['id']}).",
                "metrics": {"queue_id": entry["id"], "prompt_id": result.get("prompt_id")},
                "action_items": [{"priority": "medium", "description": "Check ComfyUI logs — SaveAnimatedWEBP may have failed or AnimateDiff nodes may be missing.", "requires_matthew": True}],
                "escalate": False,
            }

    except Exception as exc:
        entry["status"]    = "failed"
        entry["failed_at"] = datetime.now(timezone.utc).isoformat()
        _save_queue(queue)
        log.error("video_generate: failed for %s — %s", entry["id"], exc)
        return {
            "status":  "failed",
            "summary": f"Video generation failed ({entry['id']}): {exc}",
            "metrics": {"queue_id": entry["id"], "error": str(exc)},
            "action_items": [{"priority": "high", "description": str(exc), "requires_matthew": False}],
            "escalate": True,
        }
