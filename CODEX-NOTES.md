# Codex Change Note

Date: 2026-03-23

These game-engine refactor changes were made by Codex, not Claude Code.

Scope:
- Added a canonical `state/game-events.jsonl` event stream for progression events.
- Wired live chronicle writes into progression and prestige flows.
- Enriched theater events so battle outcomes can reflect real skill status and escalation data.
- Moved manual ruler XP, mobile/manual division XP, and manual prestige onto the Python progression engine.
- Added regression coverage for canonical event emission and prestige behavior.
- Added a canonical story engine with chapter progression, doctrine tracking, commander relationship state, and milestone story scenes tied to real progression events.
- Upgraded the mobile theater presentation with improved chapter cards, battle hit effects, outcome states, and richer story-scene staging.

Date: 2026-03-30

This OpenClaw gateway stability fix was made by Codex, not Claude Code.

Scope:
- Reworked `start-gateway.js` to launch OpenClaw through the real `openclaw.mjs` module path instead of invoking the Windows `openclaw.cmd` shim.
- Added a local port check for `127.0.0.1:18789` so the wrapper detects an already-running gateway and idles instead of starting a duplicate process.
- Changed wrapper restart behavior so it pauses retries when another gateway instance is already online, preventing the repeated open/crash loop.
- Verified the wrapper parses cleanly and confirmed `openclaw-gateway` was restarted under PM2 after the fix.
