# J_Claw — Personal AI Orchestration Platform

A modular, locally-hosted AI automation system running on Windows 11. J_Claw orchestrates 8 specialized agent divisions across trading, security, personal health, dev automation, game development, and media production — all routed through a persistent Node.js Mission Control server with desktop and mobile dashboards.

Built for two users: **Tyler** (PC dashboard, port 3000) and **Matthew** (mobile PWA via Tailscale, iPhone 16 Pro Max).

---

## Recent Updates

- `openclaw-gateway` restart handling was hardened so the wrapper idles when the gateway is already listening on `127.0.0.1:18789` instead of spawning duplicate crash loops.
- J_Claw and Z_Claw trading views now sync against the live Zenith cycle payload rather than stale orchestrator-only timestamps.
- `/api/trading/cycle` now exposes richer ranked strategy data for the dashboards, including profit, return, years tested, annualized stats, PF, and risk/drawdown metrics.
- The linked Zenith / Algomesh stack now supports richer ranked-strategy performance views and bounded Twelve Data `5m` history backfill so local intraday caches can grow deeper when provider credits are available.

---

## Hardware

| Component | Spec |
|---|---|
| CPU | AMD Ryzen 5 5600G |
| GPU | AMD RX 9070 XT — 16GB VRAM (RDNA 4) |
| RAM | 32GB |
| OS | Windows 11 |
| Network | Tailscale (private CGNAT mesh) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Mission Control — server.js (Node.js, PM2, port 3000)  │
│                                                         │
│  ├── dashboard/index.html   PC dashboard (Catppuccin)   │
│  ├── mobile/index.html      Mobile PWA (9500+ lines)    │
│  ├── mission_control/       Task queue + approval gates │
│  ├── state/                 Runtime state (JSON/JSONL)  │
│  └── providers/             LLM provider router         │
│       ├── OllamaProvider                                │
│       ├── AnthropicProvider                             │
│       ├── GeminiProvider                                │
│       ├── GroqProvider                                  │
│       ├── DeepSeekProvider                              │
│       └── DeterministicProvider                         │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / SSE / WebSocket
┌──────────────────────▼──────────────────────────────────┐
│  Python Skill Runtime                                   │
│                                                         │
│  runtime/orchestrators/   Per-division LLM orchestrators│
│  runtime/tools/           Shared tools + data access    │
│  ├── data_provider.py     Market data abstraction layer │
│  │    └── YfinanceProvider (swappable: CSV, Alpaca...)  │
│  ├── virtual_account.py   Paper trading engine          │
│  └── trading.py           Cycle state + agent-network   │
│  divisions/{div}/packets/ Executive Packet outputs      │
└─────────────────────────────────────────────────────────┘
```

**PM2 processes:**
- `server` — Mission Control on port 3000
- `openclaw-gateway` — OpenClaw gateway wrapper on localhost:18789

---

## LLM Routing

| Tier | Model | Hardware | Used for |
|---|---|---|---|
| Tier 0 | Deterministic (pure Python) | CPU | device-posture, breach-check, provider-health, queue-monitor |
| Tier 1 | Qwen2.5 7B instruct Q4_K_M | RX 9070 XT (ROCm) | Most skill inference |
| Tier 2 | Qwen2.5 14B instruct Q4_K_M | RX 9070 XT (ROCm) | dev-automation, deep analysis |
| Tier 2 (code) | Qwen2.5-Coder 14B Q4_K_M | RX 9070 XT (ROCm) | Dev pipeline code gen/review |
| Tier 3 | Groq 70B / Gemini / Claude | Cloud | Escalation only |

All calls are silently captured by `CaptureProvider` for BitNet fine-tuning.

---

## The 8 Divisions

| Division | Commander | Order | Key Agents |
|---|---|---|---|
| **Trading** | SEREN | Auric Veil | market-scan (1h), virtual-trader (18:00), backtester (18:00), trading-report (18:00) |
| **Opportunity** | VAEL | Dawnhunt | job-intake (3h), hard-filter (auto), funding-finder (14:00), application-tracker (10:00) |
| **Dev Automation** | KAELEN | Iron Codex | repo-monitor (3h), refactor-scan (weekly Mon), doc-update (weekly Wed), artifact-manager (23:00), dev-digest (15:00) |
| **Personal** | LYRIN | Ember Covenant | health-logger (18:00), perf-correlation (20:00), burnout-monitor (09:00), weekly-retrospective (Mon 08:00) |
| **OP-Sec** | ZETH | Nullward | device-posture (08:00), threat-surface (19:00), breach-check (Sun 13:00), cred-audit (Sun 14:00), privacy-scan (Sun 15:00), security-scan (Sun 11:00), network-monitor (03:30), opsec-digest (Sun 16:00) |
| **Production** | LYKE | Lykeon Forge | art-director (07:00), asset-catalog (12h), asset-deliver (6h), production-digest (daily), + 16 on-demand media skills |
| **Game Dev** | ARDENT | — | game-design (09:00), gamedev-digest (21:00), game-factory (Sat 04:00), + 26 on-demand design/build/test skills |
| **Sentinel** | — | Sentinel Watch | provider-health (2h), queue-monitor (2h+30m), agent-network-monitor (4h), sentinel-digest (6h) |

Each skill outputs a standardized **Executive Packet**:

```json
{
  "division": "trading",
  "skill": "market-scan",
  "generated_at": "2026-03-30T18:00:00Z",
  "status": "success|partial|failed",
  "summary": "...",
  "action_items": [{"priority": "high|normal|low", "description": "..."}],
  "metrics": {},
  "escalate": false,
  "urgency": "normal|high|critical",
  "confidence": 0.85,
  "provider_used": "ollama:qwen2.5:7b"
}
```

---

## Dashboards

### PC Dashboard (`dashboard/index.html`)
- Pixel-art Catppuccin theme
- 8 division cards with live packet metrics pulled via `/api/packets`
- Trading card now rehydrates from live Zenith cycle/status data so `[ TRADING ]`, `LAST RUN`, and the Agent-Network block stay aligned after resets and live restarts
- Agent-Network view includes ranked strategies with score, profit, return, annualized stats, PF, risk, EV, WR, OOS trades, DD, and confidence
- **Opportunity**: JOBS / TIER-A / TIER-B / TIER-C / TIER-D / FUNDING / SOURCES breakdown
- **Personal**: SLEEP / BURNOUT / LOGS / CORR-PTS / CORR-STATUS from perf-correlation
- **OP-Sec**: ANML / POST / BRCH / NET / PRIV metrics
- **Production**: HOT / COLD asset lifecycle counts
- **Sentinel bar**: QUEUE depth / provider health pills / FAILED count
- Real-time SSE: gamification events, alerts, rank-up cinematics
- All state reads go through proper `/api/*` endpoints — no direct `../state/` fetches

### Mobile PWA (`mobile/index.html`)
- Biometric (WebAuthn) + PIN auth (server-side timing-safe hash)
- 5 tabs: **Home** (division cards), **Intel** (full packets), **J_Claw** (rank/XP), **Command** (tasks/approvals), **Log** (chronicle)
- All 8 division cards with live metrics including Sentinel
- Trading tab includes a ranked strategy surface fed from the same live Zenith payload as desktop, including PF and annualized metrics
- Opportunity card: Tier A/B/C/D counts + application tracker APPS/WAITING
- OP-Sec card: 5 metrics (ANML, POST, BRCH, NET, PRIV)
- Red action-item badge on cards with high-priority items
- Realm Layer: commanders as RPG characters with battle history
- Coding chat: Claude CLI agent mode with commit approval gate
- PM2 restart button in Settings
- Push notifications (VAPID)
- Real-time SSE for all events

---

## Market Data Layer

All OHLCV data flows through a provider abstraction in `runtime/tools/data_provider.py`:

```python
from runtime.tools.data_provider import fetch_ohlcv, set_provider

ohlcv = fetch_ohlcv("SPX500", "1h")   # name resolved via assets.json
set_provider(MyBacktestProvider())     # swap backend at runtime
```

**Supported timeframes:** 1m, 5m, 15m, 1h, 4h (resampled from 1h), 1d

**Intraday (1m/5m) signal adjustments:** EMA 9/21, ATR period 7, min 20 bars, strategy builder injects tight stop-loss guidance into the LLM prompt.

---

## Zenith Trading Integration

J_Claw does not backtest strategies itself. The Trading division’s live strategy discovery, ranked winners, paper-account state, and cycle telemetry are served by the linked Zenith / Algomesh stack and proxied through Mission Control.

Primary endpoints:
- `/api/trading/cycle` — live cycle snapshot, active strategy, paper-account block, and `ranked_strategies` for the desktop/mobile dashboards
- `/api/trading/cycle/status` — live run state used by dashboard start/stop controls
- `/api/trading/cycle/run` and `/api/trading/cycle/stop` — launch and halt the linked Zenith cycle loop

Dashboard-visible ranked strategy metrics now include:
- score
- total profit `$`
- total return `%`
- years tested
- annual return `$ / yr`
- annual return `%`
- Sharpe and OOS Sharpe
- PF
- risk `%`
- EV
- win rate
- OOS trades
- drawdown
- confidence

Current intraday history note:
- the linked Zenith `5m` proxy stack uses Twelve Data plus local cache merge/backfill logic
- current bounded backfill defaults target about `2` years of intraday history per symbol
- actual refresh depth still depends on available Twelve Data credits at the time of fetch

---

## API Surface

All state is served through `/api/*` endpoints. No client reads state files directly.

| Endpoint | Method | Description |
|---|---|---|
| `/api/packets` | GET | All division Executive Packets |
| `/api/orchestrator-state` | GET | Division run status and last_run timestamps |
| `/api/agent-overrides` | GET | Agent enable/disable state |
| `/api/applications` | GET | Full applications pipeline + stats |
| `/api/jobs-seen` | GET | Total job listings seen counter |
| `/api/trade-log` | GET | Trade stats (total, win rate, avg-R) |
| `/api/health-log` | GET | Health check-in log |
| `/api/activity` | GET | Activity log feed |
| `/api/chat-history` | GET | Mission Control chat history |
| `/api/control` | GET | Task control queue status |
| `/api/queue` | GET | Sentinel task queue depth/running/failed |
| `/api/briefing` | GET/POST | Daily AI briefing |
| `/api/jobs` | GET | Pending/applied job pipeline |
| `/api/grants` | GET | Grant opportunities |
| `/api/trading/cycle` | GET | Live Zenith trading cycle payload including active strategy, paper account, and ranked strategies |
| `/api/trading/accounts` | GET | Trading account balances |
| `/api/stats/summary` | GET | Gamification XP/rank summary |
| `/api/skill` | POST | Trigger a division skill |
| `/api/agents/toggle` | POST | Enable/disable an agent |
| `/api/gamif/stream` | GET (SSE) | Real-time gamification events |

---

## Gamification

- **XP** earned per skill run, per division
- **5-tier ranks** per division (Rank 1–5)
- **Streaks** with weekly shields — per-division daily tracking
- **8 achievements**: `rulers_blessing`, `first_hunt`, `market_watcher`, `code_warden`, `healthy_habits`, `division_master`, `realm_commander`, `eternal`
- **Prestige**: all 5 divisions at Rank 5 unlocks +5% permanent XP multiplier (stackable)
- **Rank-up cinematic**: CSS overlay + Web Audio API
- **XP telemetry**: every event appended to `state/xp-history.jsonl`

---

## Production Division — Local Media Generation

All media generated entirely on-device via the AMD RX 9070 XT.

| Pipeline | Backend | Notes |
|---|---|---|
| Images | ComfyUI + SDXL (`animagine-xl-3.1`) | 6 workflow types |
| Sprites | ComfyUI + SDXL | Pixel-art variant workflow |
| Video | ComfyUI + AnimateDiff-Evolved | 16-frame WEBP @ 8fps, `mm_sdxl_v10_beta.ckpt` |
| Music | HuggingFace MusicGen + torch-directml | 8 track types, WAV output |
| Voice | Coqui XTTS v2 (CPU) | Per-commander voice cloning from reference WAVs |
| SFX | AudioCraft / local generation | Game sound effects |

Assets follow a **hot/cold TTL lifecycle**: `divisions/production/packets/` tracks total, pending, approved, delivered, hot (recent), and cold (stale) counts.

---

## Game Dev Division

The Game Dev division (commander: ARDENT) handles the full pipeline from design to playable build:

- **Design layer**: game-design, mechanic-prototype, level-design, character-designer, item-forge, enemy-designer, quest-writer, story-writer, skill-tree-builder
- **Build layer**: code-generate, code-review, code-test, build-pipeline, scene-assemble, iteration-runner, project-init
- **QA layer**: playtest-report, auto-playtest, visual-qa, balance-audit
- **Asset coordination**: asset-requester (requests from Production), asset-integration (monitors delivery)
- **Master pipeline**: `game-factory` (weekly Saturday 04:00) — chains all skills autonomously end-to-end

---

## BitNet Fine-Tuning Pipeline

Every LLM call J_Claw makes is silently captured via `CaptureProvider` to `state/qvac-captures.jsonl`. The goal: replace all cloud API calls with locally fine-tuned domain-specific models.

**Target**: BitNet b1.58 13B (TQ2_0, ~4.3 GB VRAM), fine-tuned via QVAC Fabric (Vulkan, AMD native). Expected: 130+ tok/s, zero API cost, full privacy.

```
Phase 1 — Accumulate   J_Claw runs normally → all LLM calls captured (automatic)
Phase 2 — Review       python scripts/review_captures.py --domain trading
Phase 3 — Export       python scripts/export_training_data.py --domain trading
Phase 4 — Fine-tune    llama-finetune --model bitnet-13b-tq2_0.gguf --lora-r 32 --vulkan
Phase 5 — Deploy       Router updated: skill → ["bitnet", "ollama:qwen2.5:7b", "groq"]
```

---

## Stack

| Layer | Tech |
|---|---|
| Mission Control | Node.js 20, PM2 |
| Skills | Python 3.13 |
| Local LLM | Ollama (Qwen2.5 7B / 14B / Coder 14B, AMD ROCm) |
| Cloud LLM | Groq 70B, Gemini, Anthropic Claude (escalation) |
| Image/Video | ComfyUI + AnimateDiff-Evolved |
| Music | HuggingFace Transformers + torch-directml |
| Voice | Coqui XTTS v2 |
| Market Data | yfinance in J_Claw runtime, plus linked Zenith intraday proxy feeds via Twelve Data cache/backfill |
| Mobile network | Tailscale |
| Notifications | VAPID push, Discord (Zenith bot) |

---

## Running

```bash
# Start everything
pm2 start ecosystem.config.js

# Check status
pm2 status

# View logs
pm2 logs server
pm2 logs openclaw-gateway
```

The PC dashboard is at `http://localhost:3000`.
Mobile access via Tailscale: `http://<tailscale-ip>:3000/mobile`.

---

## Security

- CORS restricted to localhost and Tailscale CGNAT range
- Mobile: server-side PIN (timing-safe) + optional WebAuthn biometric
- Windows Firewall scoped to local subnet + Tailscale
- Health and credential data never sent to cloud providers
- Sensitive state files gitignored (`state/mobile-pin.json`, `state/jclaw-stats.json`, `state/chat-history.json`, `state/health-log.json`, `state/applications.json`, `state/trade-log.json`)

---

## What's Next

- **Streak XP multiplier** — +10% per 7-day milestone, stacks to +50%
- **Stats screen** — longest streak, XP rate/day, prestige stars
- **Dashboard: Gamedev + Sentinel cards** — wire packet data into PC/mobile dashboards
- **BitNet Phase 2** — training review + first fine-tune run (Trading domain)
- **WebAuthn Face ID** — registration flow for Matthew's iPhone
- **Agent-network expansion** — live P&L and strategy-chart streaming integration
- **Market data provider upgrade** — futures-native data (Databento / CME) instead of ETF proxy intraday feeds

---

*J_Claw is a personal system. It is not a product, a framework, or a template. It is an ongoing experiment in what a single developer can automate when given enough stubbornness and a decent GPU.*
