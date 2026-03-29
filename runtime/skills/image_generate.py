"""
Image Generator — submits generation jobs to ComfyUI API and retrieves results.
Saves outputs to mobile/assets/generated/{commander}/{asset_type}/
"""

import json
import logging
import time
import uuid
import urllib.request
import urllib.error
from pathlib import Path

from runtime.config import BASE_DIR
from runtime.skills.prompt_craft import build_prompt

log = logging.getLogger(__name__)

COMFYUI_URL  = "http://127.0.0.1:8188"
OUTPUT_BASE  = BASE_DIR / "mobile" / "assets" / "generated"
WORKFLOW_DIR = BASE_DIR / "divisions" / "production" / "workflows"


def _comfyui_available() -> bool:
    try:
        urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=3)
        return True
    except Exception:
        return False


def _build_workflow(prompt_data: dict, client_id: str) -> dict:
    """Build a ComfyUI API workflow from prompt data."""
    return {
        "client_id": client_id,
        "prompt": {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "animagine-xl-3.1.safetensors"}
            },
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["1", 1],
                    "text": prompt_data["positive"]
                }
            },
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "clip": ["1", 1],
                    "text": prompt_data["negative"]
                }
            },
            "4": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width":   prompt_data["width"],
                    "height":  prompt_data["height"],
                    "batch_size": 1
                }
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "model":         ["1", 0],
                    "positive":      ["2", 0],
                    "negative":      ["3", 0],
                    "latent_image":  ["4", 0],
                    "seed":          int(time.time()) % 2**32,
                    "steps":         prompt_data["steps"],
                    "cfg":           prompt_data["cfg"],
                    "sampler_name":  prompt_data["sampler"],
                    "scheduler":     prompt_data["scheduler"],
                    "denoise":       1.0
                }
            },
            "6": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["5", 0],
                    "vae":     ["1", 2]
                }
            },
            "7": {
                "class_type": "SaveImage",
                "inputs": {
                    "images":       ["6", 0],
                    "filename_prefix": f"jclaw_{prompt_data.get('commander', 'generic')}"
                }
            }
        }
    }


def _submit_and_wait(workflow: dict, timeout_s: int = 300) -> dict:
    """Submit workflow to ComfyUI and poll for completion."""
    # Submit
    data = json.dumps(workflow).encode("utf-8")
    req  = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    prompt_id = result.get("prompt_id")
    if not prompt_id:
        raise RuntimeError(f"ComfyUI rejected prompt: {result}")

    # Poll history until done
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        time.sleep(3)
        try:
            with urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}", timeout=5) as r:
                history = json.loads(r.read())
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                images  = []
                for node_outputs in outputs.values():
                    for img in node_outputs.get("images", []):
                        images.append(img["filename"])
                return {"prompt_id": prompt_id, "images": images}
        except Exception:
            pass

    raise TimeoutError(f"ComfyUI generation timed out after {timeout_s}s")


def run(
    asset_type: str = "portrait_bust",
    commander:  str = "generic",
    subject:    str = "",
) -> dict:
    """Image Generator skill entry point."""
    if not _comfyui_available():
        log.warning("ComfyUI not reachable at %s", COMFYUI_URL)
        return {
            "status":  "partial",
            "summary": "ComfyUI is offline. Start ComfyUI and re-run image-generate.",
            "metrics": {"comfyui_online": False},
            "action_items": [{
                "priority": "high",
                "description": "Launch ComfyUI: run run_amd_gpu.bat, then retry image-generate.",
                "requires_matthew": True,
            }],
            "escalate": False,
        }

    try:
        prompt_data = build_prompt(asset_type=asset_type, commander=commander, subject=subject)
        client_id   = str(uuid.uuid4())
        workflow    = _build_workflow(prompt_data, client_id)

        log.info("Submitting image generation: %s / %s", asset_type, commander)
        result = _submit_and_wait(workflow, timeout_s=1800)

        # Ensure output directory exists
        out_dir = OUTPUT_BASE / commander / asset_type
        out_dir.mkdir(parents=True, exist_ok=True)

        images = result.get("images", [])
        log.info("Generation complete: %d image(s) — %s", len(images), images)

        return {
            "status":  "success",
            "summary": f"Generated {len(images)} image(s) for {commander} ({asset_type}). Pending review.",
            "metrics": {
                "images_generated": len(images),
                "asset_type":       asset_type,
                "commander":        commander,
                "prompt_id":        result.get("prompt_id"),
                "filenames":        images,
            },
            "action_items": [],
            "escalate":     False,
        }

    except Exception as e:
        log.error("image_generate failed: %s", e)
        return {
            "status":  "failed",
            "summary": f"Image generation failed: {e}",
            "metrics": {},
            "action_items": [{"priority": "high", "description": str(e), "requires_matthew": False}],
            "escalate": True,
        }
