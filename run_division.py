"""
Entry point for the OpenClaw Python runtime.
Called by J_Claw (via shell tool) before reading the executive packet.

Usage:
  python run_division.py opportunity job-intake
  python run_division.py opportunity funding-finder
  python run_division.py trading trading-report
  python run_division.py trading market-scan
  python run_division.py personal health-logger <reply_text>
  python run_division.py personal perf-correlation
  python run_division.py personal burnout-monitor
  python run_division.py personal personal-digest
  python run_division.py personal weekly-retrospective
  python run_division.py dev-automation repo-monitor
  python run_division.py dev-automation debug-agent <error_text> [context_file ...]
  python run_division.py dev-automation refactor-scan
  python run_division.py dev-automation security-scan
  python run_division.py dev-automation doc-update
  python run_division.py dev-automation artifact-manager
  python run_division.py dev-automation dev-digest
  python run_division.py dev pipeline '<json_spec>'
  python run_division.py op-sec agent-network-monitor
  python run_division.py op-sec mobile-audit-review
  python run_division.py production image-generate portrait_bust vael
  python run_division.py production sprite-generate vael chibi_sprite
  python run_division.py production prompt-craft portrait_bust seren
  python run_division.py production style-check <image_path> vael
  python run_division.py production image-review <image_path>
  python run_division.py production audio-test <audio_path>
  python run_division.py production video-review <video_path>
  python run_division.py production asset-catalog
  python run_division.py production storyboard-compose
  python run_division.py production continuity-check vael
  python run_division.py production asset-deliver
  python run_division.py production production-digest
  python run_division.py production game-design mechanics "inventory system"
  python run_division.py production narrative-write lore "The Dawnhunt Order"
  python run_division.py production code-generate godot "player movement controller"
  python run_division.py production sfx-generate attack
  python run_division.py production vfx-compose particle_system "fire aura" fire godot
  python run_division.py production level-design dungeon "ancient tomb"
  python run_division.py sentinel provider-health
  python run_division.py sentinel queue-monitor
  python run_division.py sentinel sentinel-digest
  python run_division.py realm-keeper grant-skill <skill_name>
  python run_division.py realm-keeper grant-base <amount> [reason]
  python run_division.py realm-keeper grant-division <division> <amount> [skill_name] [reason]
  python run_division.py realm-keeper force-prestige
  python run_division.py realm-keeper story-state
  python run_division.py realm-keeper story-choice <division> <choice_id> [choice_text]
"""

import sys
import json
import logging
import traceback
from datetime import datetime, timezone

from runtime.config import ensure_dirs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("run_division")


def run(division: str, task: str, args: list) -> dict:
    ensure_dirs()

    # ── Opportunity ───────────────────────────────────────────────────────────
    if division == "opportunity":
        from runtime.orchestrators.opportunity import run_job_intake, run_funding_finder, run_application_tracker
        if task == "job-intake":
            return run_job_intake()
        if task == "funding-finder":
            return run_funding_finder()
        if task == "application-tracker":
            return run_application_tracker()
        raise ValueError(f"Unknown task for opportunity: {task}")

    # ── Trading ───────────────────────────────────────────────────────────────
    elif division == "trading":
        from runtime.orchestrators.trading import run_trading_report, run_market_scan, run_virtual_trader, run_backtester, run_strategy_builder, run_strategy_tester, run_strategy_search
        if task == "trading-report":
            return run_trading_report()
        if task == "market-scan":
            return run_market_scan()
        if task == "virtual-trader":
            return run_virtual_trader()
        if task == "backtester":
            return run_backtester()
        if task == "strategy-builder":
            return run_strategy_builder(
                strategy_type=args[0] if args else "trend_following",
                instruments=args[1] if len(args) > 1 else "SPX500,Gold",
                timeframe=args[2] if len(args) > 2 else "1d",
                context=args[3] if len(args) > 3 else "",
            )
        if task == "strategy-tester":
            return run_strategy_tester(
                strategy_name=args[0] if args else "",
                strategy_json=args[1] if len(args) > 1 else "",
            )
        if task == "strategy-search":
            return run_strategy_search(
                market_context=args[0] if args else "",
                auto_activate=(args[1].lower() == "true") if len(args) > 1 else False,
            )
        raise ValueError(f"Unknown task for trading: {task}")

    # ── Personal ──────────────────────────────────────────────────────────────
    elif division == "personal":
        from runtime.orchestrators.personal import run_health_logger, run_perf_correlation, run_burnout_monitor, run_personal_digest, run_weekly_retrospective
        if task == "health-logger":
            reply_text = args[0] if args else ""
            if not reply_text:
                log.warning("health-logger skipped — no reply_text provided (requires Telegram check-in)")
                return {
                    "status": "skipped",
                    "reason": "no reply_text — health-logger requires Telegram interaction",
                    "escalate": False,
                }
            return run_health_logger(reply_text)
        if task == "perf-correlation":
            return run_perf_correlation()
        if task == "burnout-monitor":
            return run_burnout_monitor()
        if task == "personal-digest":
            return run_personal_digest()
        if task == "weekly-retrospective":
            return run_weekly_retrospective()
        raise ValueError(f"Unknown task for personal: {task}")

    # ── OP-Sec ────────────────────────────────────────────────────────────────
    elif division == "op-sec":
        from runtime.orchestrators.op_sec import (
            run_device_posture, run_breach_check, run_threat_surface,
            run_cred_audit, run_privacy_scan, run_security_scan, run_opsec_digest,
            run_agent_network_monitor, run_network_monitor,
        )
        if task == "device-posture":
            return run_device_posture()
        if task == "breach-check":
            return run_breach_check()
        if task == "threat-surface":
            return run_threat_surface()
        if task == "cred-audit":
            return run_cred_audit()
        if task == "privacy-scan":
            return run_privacy_scan()
        if task == "security-scan":
            return run_security_scan()
        if task == "opsec-digest":
            return run_opsec_digest()
        if task == "agent-network-monitor":
            return run_agent_network_monitor()
        if task == "network-monitor":
            return run_network_monitor()
        if task == "mobile-audit-review":
            from runtime.skills.mobile_audit_review import run as run_mobile_audit
            return run_mobile_audit()
        raise ValueError(f"Unknown task for op-sec: {task}")

    # ── Dev Automation ────────────────────────────────────────────────────────
    elif division == "dev-automation":
        from runtime.orchestrators.dev_automation import (
            run_repo_monitor, run_debug_agent, run_refactor_scan,
            run_doc_update, run_artifact_manager, run_dev_digest,
        )
        if task == "repo-monitor":
            return run_repo_monitor()
        if task == "debug-agent":
            error_text = args[0] if args else ""
            if not error_text:
                log.error("debug-agent requires error_text argument")
                sys.exit(1)
            context_files = [a for a in args[1:] if not a.startswith("--")]
            return run_debug_agent(error_text, context_files or None)
        if task == "refactor-scan":
            return run_refactor_scan()
        if task == "doc-update":
            return run_doc_update()
        if task == "artifact-manager":
            return run_artifact_manager()
        if task == "dev-digest":
            return run_dev_digest()
        raise ValueError(f"Unknown task for dev-automation: {task}")

    # ── Dev Pipeline (new — supplements dev-automation) ───────────────────────
    elif division == "dev":
        from runtime.orchestrators.dev import run_dev_pipeline
        if task == "pipeline":
            import json as _json
            spec_str = args[0] if args else "{}"
            try:
                spec = _json.loads(spec_str)
            except _json.JSONDecodeError:
                # Treat bare string as description
                spec = {"description": spec_str}
            return run_dev_pipeline(spec)
        raise ValueError(f"Unknown task for dev: {task}")

    # ── Sentinel (provider + system health) ───────────────────────────────────
    elif division == "sentinel":
        from runtime.orchestrators.sentinel import (
            run_provider_health, run_queue_monitor,
            run_agent_network_monitor, run_sentinel_digest
        )
        if task == "provider-health":
            return run_provider_health()
        if task == "queue-monitor":
            return run_queue_monitor()
        if task == "agent-network-monitor":
            return run_agent_network_monitor()
        if task == "sentinel-digest":
            return run_sentinel_digest()
        raise ValueError(f"Unknown task for sentinel: {task}")

    # ── Production Division (LYKE — The Lykeon Forge) ────────────────────────
    elif division == "production":
        from runtime.orchestrators import production as prod_orch
        task_map = {
            "prompt-craft":       lambda: prod_orch.run_prompt_craft(
                                      asset_type=args[0] if args else "portrait_bust",
                                      commander=args[1] if len(args) > 1 else "generic",
                                      subject=args[2] if len(args) > 2 else ""),
            "image-generate":     lambda: prod_orch.run_image_generate(
                                      asset_type=args[0] if args else "portrait_bust",
                                      commander=args[1] if len(args) > 1 else "generic",
                                      subject=args[2] if len(args) > 2 else ""),
            "sprite-generate":    lambda: prod_orch.run_sprite_generate(
                                      target=args[0] if args else "vael",
                                      sprite_type=args[1] if len(args) > 1 else "chibi_sprite"),
            "video-generate":     lambda: prod_orch.run_video_generate(
                                      scene_type=args[0] if args else "battle",
                                      commander=args[1] if len(args) > 1 else "generic",
                                      description=args[2] if len(args) > 2 else ""),
            "graphic-design":     lambda: prod_orch.run_graphic_design(
                                      ui_type=args[0] if args else "card_border",
                                      theme=args[1] if len(args) > 1 else "generic"),
            "style-check":        lambda: prod_orch.run_style_check(
                                      image_path=args[0] if args else "",
                                      commander=args[1] if len(args) > 1 else "generic"),
            "image-review":       lambda: prod_orch.run_image_review(
                                      image_path=args[0] if args else ""),
            "audio-test":         lambda: prod_orch.run_audio_test(
                                      audio_path=args[0] if args else ""),
            "video-review":       lambda: prod_orch.run_video_review(
                                      video_path=args[0] if args else ""),
            "asset-catalog":      lambda: prod_orch.run_asset_catalog(),
            "storyboard-compose": lambda: prod_orch.run_storyboard_compose(),
            "continuity-check":   lambda: prod_orch.run_continuity_check(
                                      commander=args[0] if args else ""),
            "music-compose":      lambda: prod_orch.run_music_compose(
                                      track_type=args[0] if args else "main_theme",
                                      division=args[1] if len(args) > 1 else "production",
                                      mood=args[2] if len(args) > 2 else "epic",
                                      tempo_bpm=int(args[3]) if len(args) > 3 else 120,
                                      duration_seconds=int(args[4]) if len(args) > 4 else 60),
            "voice-generate":     lambda: prod_orch.run_voice_generate(
                                      commander=args[0] if args else "vael",
                                      line_type=args[1] if len(args) > 1 else "greeting",
                                      emotion=args[2] if len(args) > 2 else "confident",
                                      text=args[3] if len(args) > 3 else ""),
            "asset-deliver":      lambda: prod_orch.run_asset_deliver(),
            "production-digest":  lambda: prod_orch.run_production_digest(),
            "game-design":        lambda: prod_orch.run_game_design(
                                      design_type=args[0] if args else "mechanics",
                                      topic=args[1] if len(args) > 1 else "",
                                      context=args[2] if len(args) > 2 else ""),
            "narrative-write":    lambda: prod_orch.run_narrative_write(
                                      content_type=args[0] if args else "lore",
                                      subject=args[1] if len(args) > 1 else "",
                                      context=args[2] if len(args) > 2 else ""),
            "code-generate":      lambda: prod_orch.run_code_generate(
                                      engine=args[0] if args else "godot",
                                      feature=args[1] if len(args) > 1 else "",
                                      spec=args[2] if len(args) > 2 else ""),
            "sfx-generate":       lambda: prod_orch.run_sfx_generate(
                                      sfx_type=args[0] if args else "ui_click",
                                      description=args[1] if len(args) > 1 else "",
                                      duration_s=float(args[2]) if len(args) > 2 else 0.0),
            "vfx-compose":        lambda: prod_orch.run_vfx_compose(
                                      vfx_type=args[0] if args else "particle_system",
                                      effect=args[1] if len(args) > 1 else "",
                                      style=args[2] if len(args) > 2 else "",
                                      engine=args[3] if len(args) > 3 else "godot"),
            "level-design":       lambda: prod_orch.run_level_design(
                                      level_type=args[0] if args else "dungeon",
                                      theme=args[1] if len(args) > 1 else "",
                                      constraints=args[2] if len(args) > 2 else ""),
            "model-trainer":      lambda: prod_orch.run_model_trainer(
                                      mode=args[0] if args else "review",
                                      min_captures=int(args[1]) if len(args) > 1 else 50,
                                      export_limit=int(args[2]) if len(args) > 2 else 500),
            "adapter-manager":    lambda: prod_orch.run_adapter_manager(
                                      action=args[0] if args else "status",
                                      adapter_name=args[1] if len(args) > 1 else "",
                                      task_context=args[2] if len(args) > 2 else ""),
            "qa-pipeline":        lambda: prod_orch.run_qa_pipeline(
                                      commander=args[0] if args else "generic"),
        }
        runner = task_map.get(task)
        if not runner:
            raise ValueError(f"Unknown task for production: {task}")
        return runner()

    # ── Gamedev (ARDENT, Director of the Ardent Studio) ───────────────────────
    elif division == "gamedev":
        from runtime.orchestrators import gamedev as gamedev_orch
        task_map = {
            "mechanic-prototype": lambda: gamedev_orch.run_mechanic_prototype(
                                      mechanic_type=args[0] if args else "combat",
                                      name=args[1] if len(args) > 1 else "",
                                      description=args[2] if len(args) > 2 else ""),
            "balance-audit":      lambda: gamedev_orch.run_balance_audit(
                                      audit_type=args[0] if args else "xp_curve",
                                      target=args[1] if len(args) > 1 else "",
                                      data_file=args[2] if len(args) > 2 else ""),
            "game-design":        lambda: gamedev_orch.run_game_design(
                                      design_type=args[0] if args else "mechanics",
                                      topic=args[1] if len(args) > 1 else "",
                                      context=args[2] if len(args) > 2 else ""),
            "level-design":       lambda: gamedev_orch.run_level_design(
                                      level_type=args[0] if args else "dungeon",
                                      theme=args[1] if len(args) > 1 else "",
                                      constraints=args[2] if len(args) > 2 else ""),
            "tech-spec":          lambda: gamedev_orch.run_tech_spec(
                                      spec_type=args[0] if args else "class_design",
                                      feature=args[1] if len(args) > 1 else "",
                                      engine=args[2] if len(args) > 2 else "godot"),
            "playtest-report":    lambda: gamedev_orch.run_playtest_report(
                                      session_type=args[0] if args else "full_playthrough",
                                      focus_area=args[1] if len(args) > 1 else "",
                                      notes=args[2] if len(args) > 2 else ""),
            "asset-integration":  lambda: gamedev_orch.run_asset_integration(
                                      asset_type=args[0] if args else "character_sprite",
                                      asset_path=args[1] if len(args) > 1 else "",
                                      engine=args[2] if len(args) > 2 else "godot"),
            "gamedev-digest":     lambda: gamedev_orch.run_gamedev_digest(),
            "auto-playtest":      lambda: gamedev_orch.run_auto_playtest(),
            "code-review":        lambda: gamedev_orch.run_code_review(
                                      code=args[0] if args else "",
                                      filename=args[1] if len(args) > 1 else "",
                                      engine=args[2] if len(args) > 2 else "godot"),
            "data-populate":      lambda: gamedev_orch.run_data_populate(
                                      game_context=args[0] if args else ""),
            "quest-writer":       lambda: gamedev_orch.run_quest_writer(),
        }
        runner = task_map.get(task)
        if not runner:
            raise ValueError(f"Unknown task for gamedev: {task}")
        return runner()

    # ── Realm Keeper (cross-division, pure Python) ────────────────────────────
    elif division == "realm-keeper":
        from runtime.tools.xp import (
            current_stats,
            force_prestige,
            grant_base_xp,
            grant_division_xp,
            grant_skill_xp,
        )
        from runtime.realm.story import apply_choice, current_state as current_story_state
        if task == "grant-skill":
            skill = args[0] if args else ""
            if not skill:
                log.error("grant-skill requires skill_name argument")
                sys.exit(1)
            return grant_skill_xp(skill)
        if task == "grant-base":
            amount = int(args[0]) if args else 0
            reason = args[1] if len(args) > 1 else ""
            return grant_base_xp(amount, reason)
        if task == "grant-division":
            division_key = args[0] if args else ""
            amount = int(args[1]) if len(args) > 1 else 0
            skill_name = args[2] if len(args) > 2 else "manual-bestow"
            reason = args[3] if len(args) > 3 else ""
            if not division_key:
                log.error("grant-division requires division argument")
                sys.exit(1)
            return grant_division_xp(division_key, amount, skill_name, reason)
        if task == "force-prestige":
            return force_prestige()
        if task == "story-state":
            return current_story_state()
        if task == "story-choice":
            division_key = args[0] if args else ""
            choice_id = args[1] if len(args) > 1 else ""
            choice_text = args[2] if len(args) > 2 else ""
            if not division_key or not choice_id:
                log.error("story-choice requires division and choice_id")
                sys.exit(1)
            return apply_choice(division_key, choice_id, choice_text)
        if task == "stats":
            return current_stats()
        raise ValueError(f"Unknown realm-keeper task: {task}")

    else:
        raise ValueError(f"Unknown division: {division}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    division  = sys.argv[1]
    task      = sys.argv[2]
    extra_args = sys.argv[3:]

    log.info("Starting: %s / %s", division, task)

    try:
        result = run(division, task, extra_args)
        print(json.dumps(result, indent=2, default=str))
        log.info(
            "Completed: %s / %s | status=%s escalate=%s",
            division, task,
            result.get("status", "?"),
            result.get("escalate", False),
        )
        sys.exit(0)

    except Exception as e:
        log.error("FAILED: %s / %s — %s", division, task, e)
        traceback.print_exc()
        sys.exit(1)
