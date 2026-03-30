"""
Gamedev Division Orchestrator — ARDENT, Director of the Ardent Studio.

Manages the full game development pipeline: design, prototyping, balancing,
tech specs, playtesting, and asset integration.
Reports to J_Claw with a daily studio digest.
"""

import logging

from runtime import packet
from runtime.tools.xp import grant_skill_xp
from runtime.skills import (
    mechanic_prototype,
    balance_audit,
    game_design,
    level_design,
    tech_spec,
    playtest_report,
    asset_integration,
    gamedev_digest,
)

log = logging.getLogger(__name__)

DIVISION = "gamedev"


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

def run_mechanic_prototype(mechanic_type: str = "combat", name: str = "", description: str = "") -> dict:
    result = mechanic_prototype.run(mechanic_type=mechanic_type, name=name, description=description)
    pkt    = _build_packet("mechanic-prototype", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("mechanic-prototype")
    log.info("ARDENT: mechanic-prototype %s/%s → %s", mechanic_type, name, result.get("status"))
    return pkt


def run_balance_audit(audit_type: str = "xp_curve", target: str = "", data_file: str = "") -> dict:
    result = balance_audit.run(audit_type=audit_type, target=target, data_file=data_file)
    pkt    = _build_packet("balance-audit", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("balance-audit")
    log.info("ARDENT: balance-audit %s/%s → %s", audit_type, target, result.get("status"))
    return pkt


def run_game_design(design_type: str = "mechanics", topic: str = "", context: str = "") -> dict:
    result = game_design.run(design_type=design_type, topic=topic, context=context)
    pkt    = _build_packet("game-design", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("game-design")
    log.info("ARDENT: game-design %s/%s → %s", design_type, topic, result.get("status"))
    return pkt


def run_level_design(level_type: str = "dungeon", theme: str = "", constraints: str = "") -> dict:
    result = level_design.run(level_type=level_type, theme=theme, constraints=constraints)
    pkt    = _build_packet("level-design", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("level-design")
    log.info("ARDENT: level-design %s/%s → %s", level_type, theme, result.get("status"))
    return pkt


def run_tech_spec(feature: str = "", design_context: str = "", engine: str = "godot", spec_type: str = "class_design") -> dict:
    result = tech_spec.run(feature=feature, design_context=design_context, engine=engine, spec_type=spec_type)
    pkt    = _build_packet("tech-spec", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("tech-spec")
    log.info("ARDENT: tech-spec %s/%s → %s", spec_type, feature, result.get("status"))
    return pkt


def run_playtest_report(session_type: str = "full_playthrough", focus_area: str = "", notes: str = "") -> dict:
    result = playtest_report.run(session_type=session_type, focus_area=focus_area, notes=notes)
    pkt    = _build_packet("playtest-report", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("playtest-report")
    log.info("ARDENT: playtest-report %s/%s → %s", session_type, focus_area, result.get("status"))
    return pkt


def run_asset_integration(asset_type: str = "character_sprite", asset_path: str = "", engine: str = "godot") -> dict:
    result = asset_integration.run(asset_type=asset_type, asset_path=asset_path, engine=engine)
    pkt    = _build_packet("asset-integration", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("asset-integration")
    log.info("ARDENT: asset-integration %s/%s → %s", asset_type, engine, result.get("status"))
    return pkt


def run_gamedev_digest() -> dict:
    result = gamedev_digest.run()
    pkt    = _build_packet("gamedev-digest", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("gamedev-digest")
    log.info("ARDENT: gamedev-digest → %s", result.get("status"))
    return pkt
