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

Date: 2026-03-30

This OP-Sec and Opportunity division verification update was made by Codex, not Claude Code.

Before:
- `network-monitor` was logged as failed at `2026-03-30T06:30:02.114Z` with `Unknown task for op-sec: network-monitor`.
- `application-tracker` was logged as failed at `2026-03-30T13:00:01.631Z` with `Unknown task for opportunity: application-tracker`.

After:
- Verified the current `run_division.py` source already includes both task routes, and the current orchestrators already implement both runners.
- Triggered `network-monitor` and `application-tracker` through the live localhost `openclaw` skill endpoint after the service restart.
- Confirmed both completed successfully on `2026-03-30`:
  - `network-monitor complete` at `2026-03-30T18:27:09.978Z`
  - `application-tracker complete` at `2026-03-30T18:27:12.829Z`
- Confirmed fresh packet writes for `divisions/op-sec/packets/network-monitor.json` and `divisions/opportunity/packets/application-tracker.json`.

Conclusion:
- No additional source patch was required for these two tasks.
- The earlier failures were from an older runtime state before the current `openclaw` restart, not from missing task support in the current code on disk.
