# J_Claw — Personal AI Orchestration Platform

A modular, locally-hosted AI automation system running on Windows 11. J_Claw orchestrates 7 specialized agent divisions across trading, security, personal health, dev automation, and media production — all routed through a persistent Node.js Mission Control server with desktop and mobile dashboards.

Built for two users: **Tyler** (PC dashboard, port 3000) and **Matthew** (mobile PWA via Tailscale, iPhone 16 Pro Max).

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
│       └── DeterministicProvider                         │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / SSE / WebSocket
┌──────────────────────▼──────────────────────────────────┐
│  Python Skill Runtime                                   │
│                                                         │
│  runtime/orchestrators/   Per-division LLM orchestrators│
│  divisions/{div}/packets/ Executive Packet outputs      │
└─────────────────────────────────────────────────────────┘
```

**PM2 processes:**
- `server` — Mission Control on port 3000
- `openclaw-gateway` — Zenith/Discord bot on localhost:40000 (Ollama `zenith-expert`)

---

## The 7 Divisions

| Division | Commander | Order | Cron Schedule |
|---|---|---|---|
| **Trading** | SEREN | Auric Veil | market-scan (2h), virtual-trader (18:00), backtester (18:05), trading-report (18:10) |
| **Opportunity** | VAEL | Dawnhunt | job-intake (3h), hard-filter (auto), funding-finder (14:00) |
| **Dev Automation** | KAELEN | Iron Codex | repo-monitor (02:00), refactor-scan (02:30), security-scan (11:00), doc-update (13:00), artifact-manager (03:00), dev-digest (15:00) |
| **Personal** | LYRIN | Ember Covenant | health-logger (18:00), perf-correlation (20:00), burnout-monitor (21:00), personal-digest (21:30) |
| **OP-Sec** | ZETH | Nullward | device-posture (08:00), breach-check (14:00), threat-surface (19:00), cred-audit (15:00), privacy-scan (16:00), opsec-digest (16:30), mobile-audit-review (23:00) |
| **Production** | LYKE | Lykeon Forge | prompt-craft, image-generate, sprite-generate, video-generate (on-demand), asset-deliver (6h) |
| **Sentinel** | VEIL | Sentinel Watch | provider-health (2h), queue-monitor (continuous) |

Each skill outputs a standardized **Executive Packet**:

```json
{
  "division": "trading",
  "skill": "market-scan",
  "generated_at": "2026-03-28T18:00:00Z",
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
- 7 division cards with live packet data, XP, and rank
- Real-time SSE: gamification events, alerts, rank-up cinematics

### Mobile PWA (`mobile/index.html`)
- Biometric (WebAuthn) + PIN auth (server-side timing-safe hash)
- 5 tabs: **Home** (division cards), **Intel** (full packets), **J_Claw** (rank/XP), **Command** (tasks/approvals), **Log** (chronicle)
- Realm Layer: commanders as RPG characters with battle history
- Coding chat: Claude CLI agent mode with commit approval gate
- PM2 restart button in Settings
- Push notifications (VAPID)
- Real-time SSE for all events

---

## Gamification

- **XP** earned per skill run, per division
- **5-tier ranks** per division (Rank 1–5)
- **Streaks** with weekly shields
- **8 achievements**: `first_hunt`, `market_watcher`, `code_warden`, `healthy_habits`, and more
- **Prestige**: all 5 divisions at Rank 5 unlocks +5% permanent XP multiplier (stackable)
- **Rank-up cinematic**: CSS overlay + Web Audio API

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

Assets follow a **hot/cold TTL lifecycle**: `divisions/production/packets/` tracks total, pending, approved, delivered, hot, and cold counts.

---

## BitNet Fine-Tuning Pipeline

Every LLM call J_Claw makes is silently captured via `CaptureProvider` to `state/training-capture.jsonl`. The goal: replace all cloud API calls with locally fine-tuned domain-specific models.

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
| Local LLM | Ollama (Qwen2.5 7B / Coder 14B, AMD ROCm/Vulkan) |
| Cloud LLM | Groq 70B, Gemini, Anthropic Claude (escalation) |
| Image/Video | ComfyUI + AnimateDiff-Evolved |
| Music | HuggingFace Transformers + torch-directml |
| Voice | Coqui XTTS v2 |
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
- Sensitive state files gitignored

---

## What's Next

- **Streak XP multiplier** — +10% per 7-day milestone, stacks to +50%
- **Stats screen** — longest streak, XP rate/day, prestige stars
- **Rank-up overlay** — enhanced sound design
- **WebAuthn Face ID** — registration flow for Matthew's iPhone
- **Agent-network expansion** — live P&L streaming integration
- **Voice clone status** — Production division UI integration
- **BitNet Phase 2** — training review + first fine-tune run (Trading domain)

---

*J_Claw is a personal system. It is not a product, a framework, or a template. It is an ongoing experiment in what a single developer can automate when given enough stubbornness and a decent GPU.*
