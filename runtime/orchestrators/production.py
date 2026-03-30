"""
Production Division Orchestrator — LYKE, Architect of the Lykeon Forge.

Manages the full creative asset pipeline: generation, QA, cataloging, and delivery.
Reports to J_Claw with a production digest summarizing pipeline health.
"""

import logging
from datetime import datetime, timezone

from runtime import packet
from runtime.tools.xp import grant_skill_xp
from runtime.skills import (
    prompt_craft,
    image_generate,
    sprite_generate,
    video_generate,
    graphic_design,
    style_check,
    image_review,
    audio_test,
    video_review,
    asset_catalog,
    storyboard_compose,
    continuity_check,
    asset_deliver,
    music_compose,
    voice_generate,
    game_design,
    narrative_write,
    code_generate,
    sfx_generate,
    vfx_compose,
    level_design,
    model_trainer,
    adapter_manager,
)

log = logging.getLogger(__name__)

DIVISION = "production"


def _build_packet(skill: str, result: dict) -> dict:
    return packet.build(
        division      = DIVISION,
        skill         = skill,
        status        = result.get("status", "failed"),
        summary       = result.get("summary", ""),
        action_items  = result.get("action_items", []),
        metrics       = result.get("metrics", {}),
        escalate      = result.get("escalate", False),
        urgency       = "high" if result.get("escalate") else "normal",
    )


# ── Individual skill runners ──────────────────────────────────────────────────

def run_prompt_craft(asset_type: str = "portrait_bust", commander: str = "generic", subject: str = "") -> dict:
    result = prompt_craft.run(asset_type=asset_type, commander=commander, subject=subject)
    pkt    = _build_packet("prompt-craft", result)
    packet.write(pkt)
    grant_skill_xp("prompt-craft")
    log.info("LYKE: prompt-craft complete")
    return pkt


def run_image_generate(asset_type: str = "portrait_bust", commander: str = "generic", subject: str = "") -> dict:
    result = image_generate.run(asset_type=asset_type, commander=commander, subject=subject)
    pkt    = _build_packet("image-generate", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("image-generate")
    log.info("LYKE: image-generate complete — %s", result.get("status"))
    return pkt


def run_sprite_generate(target: str = "vael", sprite_type: str = "chibi_sprite") -> dict:
    result = sprite_generate.run(target=target, sprite_type=sprite_type)
    pkt    = _build_packet("sprite-generate", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("sprite-generate")
    log.info("LYKE: sprite-generate — %s / %s → %s", target, sprite_type, result.get("status"))
    return pkt


def run_video_generate(scene_type: str = "battle", commander: str = "generic", description: str = "") -> dict:
    result = video_generate.run(scene_type=scene_type, commander=commander, description=description)
    pkt    = _build_packet("video-generate", result)
    packet.write(pkt)
    grant_skill_xp("video-generate")
    log.info("LYKE: video-generate queued — %s / %s", scene_type, commander)
    return pkt


def run_graphic_design(ui_type: str = "card_border", theme: str = "generic", subject: str = "") -> dict:
    result = graphic_design.run(ui_type=ui_type, theme=theme, subject=subject)
    pkt    = _build_packet("graphic-design", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("graphic-design")
    log.info("LYKE: graphic-design — %s / %s → %s", ui_type, theme, result.get("status"))
    return pkt


def run_style_check(image_path: str = "", commander: str = "generic") -> dict:
    result = style_check.run(image_path=image_path, commander=commander)
    pkt    = _build_packet("style-check", result)
    packet.write(pkt)
    grant_skill_xp("style-check")
    log.info("LYKE: style-check → %s", result.get("status"))
    return pkt


def run_image_review(image_path: str = "") -> dict:
    result = image_review.run(image_path=image_path)
    pkt    = _build_packet("image-review", result)
    packet.write(pkt)
    grant_skill_xp("image-review")
    log.info("LYKE: image-review → %s", result.get("status"))
    return pkt


def run_audio_test(audio_path: str = "") -> dict:
    result = audio_test.run(audio_path=audio_path)
    pkt    = _build_packet("audio-test", result)
    packet.write(pkt)
    grant_skill_xp("audio-test")
    log.info("LYKE: audio-test → %s", result.get("status"))
    return pkt


def run_video_review(video_path: str = "") -> dict:
    result = video_review.run(video_path=video_path)
    pkt    = _build_packet("video-review", result)
    packet.write(pkt)
    grant_skill_xp("video-review")
    log.info("LYKE: video-review → %s", result.get("status"))
    return pkt


def run_asset_catalog() -> dict:
    result = asset_catalog.run()
    pkt    = _build_packet("asset-catalog", result)
    packet.write(pkt)
    grant_skill_xp("asset-catalog")
    log.info("LYKE: asset-catalog → %s", result.get("status"))
    return pkt


def run_storyboard_compose() -> dict:
    result = storyboard_compose.run()
    pkt    = _build_packet("storyboard-compose", result)
    packet.write(pkt)
    grant_skill_xp("storyboard-compose")
    log.info("LYKE: storyboard-compose → %d shots", result.get("metrics", {}).get("shots_composed", 0))
    return pkt


def run_continuity_check(commander: str = "") -> dict:
    result = continuity_check.run(commander=commander)
    pkt    = _build_packet("continuity-check", result)
    packet.write(pkt)
    grant_skill_xp("continuity-check")
    log.info("LYKE: continuity-check %s → %s", commander, result.get("status"))
    return pkt


def run_asset_deliver() -> dict:
    result = asset_deliver.run()
    pkt    = _build_packet("asset-deliver", result)
    packet.write(pkt)
    grant_skill_xp("asset-deliver")
    log.info("LYKE: asset-deliver → %d delivered", result.get("metrics", {}).get("delivered", 0))
    return pkt


def run_music_compose(
    track_type: str = "main_theme",
    division: str = "production",
    mood: str = "epic",
    tempo_bpm: int = 120,
    duration_seconds: int = 60,
) -> dict:
    result = music_compose.run(
        track_type=track_type,
        division=division,
        mood=mood,
        tempo_bpm=tempo_bpm,
        duration_seconds=duration_seconds,
    )
    pkt = _build_packet("music-compose", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("music-compose")
    log.info("LYKE: music-compose → %s [%s/%s]", result.get("status"), division, track_type)
    return pkt


def run_voice_generate(
    commander: str = "vael",
    line_type: str = "greeting",
    emotion: str = "confident",
    text: str = "",
) -> dict:
    result = voice_generate.run(
        commander=commander,
        line_type=line_type,
        emotion=emotion,
        text=text,
    )
    pkt = _build_packet("voice-generate", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("voice-generate")
    log.info("LYKE: voice-generate → %s [%s/%s]", result.get("status"), commander, line_type)
    return pkt


# ── Game Dev Team skills ──────────────────────────────────────────────────────

def run_game_design(design_type: str = "mechanics", topic: str = "", context: str = "") -> dict:
    result = game_design.run(design_type=design_type, topic=topic, context=context)
    pkt    = _build_packet("game-design", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("game-design")
    log.info("LYKE: game-design %s/%s → %s", design_type, topic, result.get("status"))
    return pkt


def run_narrative_write(content_type: str = "lore", subject: str = "", context: str = "") -> dict:
    result = narrative_write.run(content_type=content_type, subject=subject, context=context)
    pkt    = _build_packet("narrative-write", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("narrative-write")
    log.info("LYKE: narrative-write %s/%s → %s", content_type, subject, result.get("status"))
    return pkt


def run_code_generate(engine: str = "godot", feature: str = "", spec: str = "") -> dict:
    result = code_generate.run(engine=engine, feature=feature, spec=spec)
    pkt    = _build_packet("code-generate", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("code-generate")
    log.info("LYKE: code-generate %s/%s → %s", engine, feature, result.get("status"))
    return pkt


def run_sfx_generate(sfx_type: str = "ui_click", description: str = "", duration_s: float = 0.0) -> dict:
    result = sfx_generate.run(sfx_type=sfx_type, description=description, duration_s=duration_s)
    pkt    = _build_packet("sfx-generate", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("sfx-generate")
    log.info("LYKE: sfx-generate %s → %s", sfx_type, result.get("status"))
    return pkt


def run_vfx_compose(vfx_type: str = "particle_system", effect: str = "", style: str = "", engine: str = "godot") -> dict:
    result = vfx_compose.run(vfx_type=vfx_type, effect=effect, style=style, engine=engine)
    pkt    = _build_packet("vfx-compose", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("vfx-compose")
    log.info("LYKE: vfx-compose %s/%s → %s", vfx_type, effect, result.get("status"))
    return pkt


def run_level_design(level_type: str = "dungeon", theme: str = "", constraints: str = "") -> dict:
    result = level_design.run(level_type=level_type, theme=theme, constraints=constraints)
    pkt    = _build_packet("level-design", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("level-design")
    log.info("LYKE: level-design %s/%s → %s", level_type, theme, result.get("status"))
    return pkt


# ── QVAC Pipeline ────────────────────────────────────────────────────────────

def run_model_trainer(mode: str = "review", min_captures: int = 50, export_limit: int = 500) -> dict:
    result = model_trainer.run(mode=mode, min_captures=min_captures, export_limit=export_limit)
    pkt    = _build_packet("model-trainer", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("model-trainer")
    log.info("LYKE: model-trainer mode=%s → %s", mode, result.get("status"))
    return pkt


def run_adapter_manager(action: str = "status", adapter_name: str = "", task_context: str = "") -> dict:
    result = adapter_manager.run(action=action, adapter_name=adapter_name, task_context=task_context)
    pkt    = _build_packet("adapter-manager", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("adapter-manager")
    log.info("LYKE: adapter-manager action=%s → %s", action, result.get("status"))
    return pkt


# ── Production Digest ─────────────────────────────────────────────────────────

def run_production_digest() -> dict:
    """
    LYKE's executive report to J_Claw.
    Runs catalog + storyboard, then synthesizes pipeline health.
    """
    catalog_result     = asset_catalog.run()
    storyboard_result  = storyboard_compose.run()
    deliver_result     = asset_deliver.run()

    catalog_m    = catalog_result.get("metrics", {})
    storyboard_m = storyboard_result.get("metrics", {})
    deliver_m    = deliver_result.get("metrics", {})

    total_assets  = catalog_m.get("total", 0)
    pending       = catalog_m.get("pending", 0)
    approved      = catalog_m.get("approved", 0)
    delivered     = deliver_m.get("delivered", 0)
    shots_queued  = storyboard_m.get("shots_composed", 0)

    # Determine overall status
    if pending > 5:
        status  = "partial"
        summary = (
            f"The Forge is active. {total_assets} total assets — {pending} pending review. "
            f"{shots_queued} storyboard shots queued for production. "
            f"{delivered} assets delivered to game this cycle. "
            "LYKE requests review of pending assets."
        )
    else:
        status  = "success"
        summary = (
            f"The Forge burns steady. {total_assets} assets in catalog. "
            f"{approved} approved, {delivered} delivered. "
            f"{shots_queued} storyboard shots queued for next generation run. "
            "Pipeline health: nominal."
        )

    pkt = packet.build(
        division     = DIVISION,
        skill        = "production-digest",
        status       = status,
        summary      = summary,
        action_items = [{
            "priority":        "normal",
            "description":     f"{pending} asset(s) in catalog need approval — update status in state/asset-catalog.json",
            "requires_matthew": True,
        }] if pending > 0 else [],
        metrics      = {
            "total_assets":   total_assets,
            "pending_review": pending,
            "approved":       approved,
            "delivered":      delivered,
            "shots_queued":   shots_queued,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        },
        escalate     = False,
        urgency      = "normal",
    )

    packet.write(pkt)
    grant_skill_xp("production-digest")
    log.info("LYKE: production-digest complete — %s", status)
    return pkt
