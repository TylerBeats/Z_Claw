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
    auto_playtest,
    code_review,
    data_populate,
    quest_writer,
    project_init,
    character_designer,
    enemy_designer,
    item_forge,
    story_writer,
    skill_tree_builder,
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


def run_auto_playtest(**kwargs) -> dict:
    result = auto_playtest.run(**kwargs)
    pkt    = _build_packet("auto-playtest", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("auto-playtest")
    log.info("ARDENT: auto-playtest → %s", result.get("status"))
    return pkt


def run_code_review(code: str = "", filename: str = "", engine: str = "godot") -> dict:
    result = code_review.run(code=code, filename=filename, engine=engine)
    pkt    = _build_packet("code-review", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("code-review")
    log.info("ARDENT: code-review %s → %s", filename, result.get("status"))
    return pkt


def run_data_populate(game_context: str = "") -> dict:
    result = data_populate.run(game_context=game_context)
    pkt    = _build_packet("data-populate", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("data-populate")
    log.info("ARDENT: data-populate → %s", result.get("status"))
    return pkt


def run_quest_writer(**kwargs) -> dict:
    result = quest_writer.run(**kwargs)
    pkt    = _build_packet("quest-writer", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("quest-writer")
    log.info("ARDENT: quest-writer → %s", result.get("status"))
    return pkt


def run_project_init(target: str = "godot", project_name: str = "", window_width: int = 1280, window_height: int = 720) -> dict:
    result = project_init.run(target=target, project_name=project_name, window_width=window_width, window_height=window_height)
    pkt    = _build_packet("project-init", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("project-init")
    log.info("ARDENT: project-init %s/%s → %s", target, project_name, result.get("status"))
    return pkt


def run_character_designer(name: str = "", role: str = "hero", class_type: str = "warrior", prompt: str = "") -> dict:
    result = character_designer.run(name=name, role=role, class_type=class_type, prompt=prompt)
    pkt    = _build_packet("character-designer", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("character-designer")
    log.info("ARDENT: character-designer %s/%s → %s", role, class_type, result.get("status"))
    return pkt


def run_enemy_designer(name: str = "", enemy_type: str = "minion", difficulty: str = "medium", prompt: str = "") -> dict:
    result = enemy_designer.run(name=name, enemy_type=enemy_type, difficulty=difficulty, prompt=prompt)
    pkt    = _build_packet("enemy-designer", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("enemy-designer")
    log.info("ARDENT: enemy-designer %s/%s → %s", enemy_type, difficulty, result.get("status"))
    return pkt


def run_item_forge(item_name: str = "", item_type: str = "weapon", rarity: str = "common", prompt: str = "") -> dict:
    result = item_forge.run(item_name=item_name, item_type=item_type, rarity=rarity, prompt=prompt)
    pkt    = _build_packet("item-forge", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("item-forge")
    log.info("ARDENT: item-forge %s/%s → %s", item_type, rarity, result.get("status"))
    return pkt


def run_story_writer(section: str = "overview", act_number: int = 1, prompt: str = "") -> dict:
    result = story_writer.run(section=section, act_number=act_number, prompt=prompt)
    pkt    = _build_packet("story-writer", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("story-writer")
    log.info("ARDENT: story-writer %s → %s", section, result.get("status"))
    return pkt


def run_skill_tree_builder(class_type: str = "warrior", tree_name: str = "", prompt: str = "") -> dict:
    result = skill_tree_builder.run(class_type=class_type, tree_name=tree_name, prompt=prompt)
    pkt    = _build_packet("skill-tree-builder", result)
    packet.write(pkt)
    if result.get("status") in ("success", "partial"):
        grant_skill_xp("skill-tree-builder")
    log.info("ARDENT: skill-tree-builder %s/%s → %s", class_type, tree_name, result.get("status"))
    return pkt
