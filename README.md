# J_Claw — Personal AI Orchestration System

A modular, locally-hosted AI automation platform built on Windows 11. J_Claw runs a persistent Mission Control server that orchestrates Python skill agents across multiple life domains, with a desktop dashboard and mobile PWA accessible over a private network.

J_Claw is also building toward full local AI independence — capturing every LLM call it makes to fine-tune domain-specific BitNet models that run privately, for free, on consumer hardware.

---

## Architecture

```
Mission Control (Node.js / PM2)
  └── server.js                 # HTTP server, WebSocket, SSE, skill runner
      ├── dashboard/            # Desktop dashboard (vanilla JS PWA)
      ├── mobile/               # Mobile PWA (Tailscale access)
      └── run_division.py       # Python runtime entry point

Python Skill Runtime
  └── runtime/
      ├── orchestrators/        # Per-division LLM orchestrators
      ├── skills/               # Individual skill modules
      └── tools/                # Shared data tools (trading, XP, state, etc.)

Divisions (agents)
  ├── trading/                  # Market scans, virtual paper trading, backtesting
  ├── opportunity/              # Job intake, filtering, funding discovery
  ├── dev-automation/           # Repo monitoring, refactor scans, code review
  ├── personal/                 # Health logging, performance correlation, burnout monitoring
  ├── op-sec/                   # Device posture, breach monitoring, privacy scans
  ├── production/               # AI media generation (images, sprites, audio, video)
  └── sentinel/                 # System health, provider uptime, queue monitoring

State
  └── state/                    # jclaw-stats.json, xp-history.jsonl, anim-queue.json, etc.
```

---

## Key Features

- **Multi-division agent orchestration** — each division runs scheduled Python skills via `run_division.py`, with results written as JSON packets
- **LLM routing** — Tier 0 (pure Python), Tier 1 (local Ollama 7B), Tier 2 (GPT-4o) per skill
- **Gamification** — XP, per-division ranks, streaks, streak multipliers, prestige system, achievements
- **Theater system** — animated battle scenes queued from division activity, viewable on both desktop and mobile
- **Real-time updates** — WebSocket + SSE streams push live events to dashboard and mobile
- **Realm Layer** — commanders (VAEL, SEREN, KAELEN, LYRIN, ZETH, LYKE) represent each division's identity
- **Virtual paper trading** — SPX500 and Gold simulation via yfinance with real market data, no broker required
- **Mobile PWA** — full-featured mobile interface accessible over Tailscale private network

---

## Divisions & Agents

| Division | Key Agents | Schedule |
|---|---|---|
| **Trading** | market-scan, virtual-trader, backtester, trading-report | Hourly / Daily 18:00 |
| **Opportunity** | job-intake, hard-filter, funding-finder | Every 3h / Daily 14:00 |
| **Dev Automation** | repo-monitor, refactor-scan, debug-agent, dev-digest | Daily |
| **Personal** | health-logger, perf-correlation, burnout-monitor | Daily |
| **Op-Sec** | device-posture, threat-surface, breach-check, cred-audit, privacy-scan | Daily / Weekly |
| **Production** | image-generate, sprite-generate, prompt-craft, asset-catalog, production-digest | On-demand / Daily |
| **Sentinel** | provider-health, queue-monitor, sentinel-digest | Every 30min / Daily |

---

## Stack

- **Runtime**: Node.js 20 (Mission Control), Python 3.13 (skills)
- **Process manager**: PM2
- **Local LLM**: Ollama (Qwen2.5 7B / Coder 14B via AMD RX 9070 XT + ROCm/Vulkan)
- **Cloud LLM fallback**: Groq (70B), DeepSeek, Gemini, Claude (escalation only)
- **Fine-tuning target**: BitNet b1.58 13B via QVAC Fabric (Vulkan, AMD native)
- **Image generation**: ComfyUI (local)
- **Trading data**: yfinance
- **Private networking**: Tailscale
- **Notifications**: Telegram bot, Discord (Zenith bot)

---

## BitNet Fine-Tuning Pipeline

J_Claw is designed to eventually replace all external AI API calls with locally fine-tuned models that know its specific domain — trading signals, codebase patterns, operator interaction style — running entirely on-device.

### Why

Every LLM call J_Claw makes is a training example. A prompt containing live market data sent to `market-scan` and the resulting signal analysis is exactly the kind of pair that, accumulated over time, teaches a model to reason about *your* instruments, *your* strategy, *your* risk parameters. The same applies to coding tasks, security scans, and operator chat.

Cloud APIs are used as the initial teacher. The goal is to graduate to a student that runs locally, faster, for free, with full privacy.

### How It Works

A `CaptureProvider` wrapper sits invisibly between J_Claw's skill layer and every AI model it calls. It is injected at the provider router — the single chokepoint all LLM calls flow through — so zero skill code was changed. When any skill calls `.chat()`, the wrapper:

1. Forwards the call to the real provider (Ollama, Groq, etc.) unchanged
2. Records the full prompt, the response, the task type, the provider used, and the latency
3. Appends one JSON line to `state/training-capture.jsonl`
4. Returns the response to the skill — which never knows capture happened

Short responses (< 30 chars) and pure-Python deterministic calls are skipped automatically.

```
Skill calls .chat(messages)
        │
        ▼
CaptureProvider.chat()          ← intercepts here
        │
        ├── writes to training-capture.jsonl (fire-and-forget)
        │
        ▼
inner_provider.chat(messages)   ← real call, unmodified
        │
        ▼
response returned to skill      ← skill sees nothing different
```

### Capture File Format

Each line in `state/training-capture.jsonl`:

```json
{
  "ts": "2026-03-26T18:00:00+00:00",
  "task_type": "market-scan",
  "provider_id": "ollama:qwen2.5:7b-instruct-q4_K_M",
  "messages": [
    {"role": "system", "content": "You are the Signal Keeper..."},
    {"role": "user", "content": "Analyze today's market data for SPX500..."}
  ],
  "response": "SPX500 up 0.8% — EMA20 holding above EMA50, ATR expanding...",
  "latency_ms": 1243,
  "json_mode": false
}
```

### Workflow

```
Phase 1 — Accumulate (ongoing, automatic)
  J_Claw runs normally → every LLM call captured to training-capture.jsonl
  Target: 500–2000 quality pairs per domain (est. 4–6 weeks of normal operation)

Phase 2 — Review (manual, before training)
  python scripts/review_captures.py --domain trading
  Browse pairs interactively: [k]eep / [d]elete / [s]kip
  Approved pairs written to state/training-approved.jsonl

Phase 3 — Export (one command)
  python scripts/export_training_data.py --domain trading
  Outputs state/training-exports/training-trading.jsonl in llama-finetune format

Phase 4 — Fine-tune (AMD RX 9070 XT, Vulkan backend)
  llama-finetune --model bitnet-13b-tq2_0.gguf \
                 --train-data training-trading.jsonl \
                 --lora-r 32 --ctx 2048 --vulkan

Phase 5 — Deploy
  llama-server --model bitnet-13b.gguf --lora adapters/trading-v1/ --port 8082
  Router updated: "market-scan" → ["bitnet", "ollama:qwen2.5:7b", "groq"]
```

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/export_training_data.py --stats` | Show capture stats by domain/provider |
| `scripts/export_training_data.py --domain trading` | Export trading domain for fine-tuning |
| `scripts/review_captures.py --domain coding` | Interactively approve/reject coding pairs |

### Target Hardware

The fine-tuning target is a **BitNet b1.58 13B** model (Microsoft) in TQ2_0 format (~4.3 GB VRAM), trained and served on an AMD RX 9070 XT (16 GB GDDR6, RDNA 4) using [QVAC Fabric](https://github.com/tetherto/qvac-fabric-llm.cpp) — the first open framework for BitNet LoRA fine-tuning on consumer GPUs via Vulkan.

Expected outcome: 130+ tokens/second inference, zero API cost, full trading strategy privacy, domain accuracy exceeding general-purpose 7B models for J_Claw-specific tasks.

---

## Security

- CORS restricted to localhost and private Tailscale CGNAT range
- Bearer token + PIN authentication for mobile access
- Timing-safe PIN comparison (`crypto.timingSafeEqual`)
- Windows Firewall rule scoped to local subnet + Tailscale
- Health and credential data stays local — no API fallback for sensitive skills

---

## Changelog

See commit history for detailed change notes. Major milestones:

- **2026-03-26** — BitNet fine-tuning pipeline: `CaptureProvider` wrapper captures all LLM calls to `state/training-capture.jsonl`; export and review scripts added; router wired — zero changes to any skill
- **2026-03-22** — Trading account growth tracking fixed; backtester wired to skill runner; source label corrected (`virtual_account` vs `dry_run`)
- **2026-03-22** — Phase 2 gamification: auto-prestige, streak multiplier SSE, full-screen rank-up overlay, stats division breakdown
- **2026-03-22** — Security hardening: CORS preflight fix, timing-safe PIN, all op-sec division agents wired
- **2026-03-22** — Production division: storage increased to 10GB, all agent skill keys verified
- **Earlier** — Virtual paper trader, backtester, market-scan, trading-report pipeline built
- **Earlier** — Mobile PWA with haptics, XP floats, commander panels, theater system
- **Earlier** — Realm Layer architecture: commanders, orders, chronicle, directive endpoint
