---
name: backtester
description: Read the latest cycle state from agent-network, extract backtest metrics and strategy selection results, detect strategy changes, and compile an executive packet for the trading division chief. Run by division-chief-trading at 18:00 daily after trading-report.
schedule: daily 18:00
division: trading
runner: division-chief-trading
---

## Trigger
Called by division-chief-trading at 18:00 daily, after trading-report completes.
Do NOT call Claude directly — this skill runs under the local GGUF division orchestrator.

## Prerequisites
- `C:\Users\Tyler\agent-network\state\spx500_cycle_state.json` must exist
- If missing: return `status: partial`, note "agent-network cycle state not found", do not escalate

## Data Sources

### Cycle State File
```
C:\Users\Tyler\agent-network\state\spx500_cycle_state.json
```
Contains:
- `cycle_number` — current cycle integer
- `active_strategy` — full strategy object with all metrics
- Additional strategy candidates (ranked list, if present)

### Previous Backtester Packet (for comparison)
```
divisions/trading/packets/backtester.json
```
Used to detect strategy changes between cycles. If missing, skip comparison step.

## Steps

1. **Load cycle state**
   - Read `spx500_cycle_state.json`
   - Parse `cycle_number` and `active_strategy` object
   - Extract these fields from `active_strategy`:
     - `strategy_id`, `strategy_name`
     - `sharpe`, `sortino`, `win_rate`, `profit_factor`
     - `max_drawdown`, `avg_r`, `avg_win_r`, `avg_loss_r`, `rr_ratio`
     - `theoretical_ev_r`, `empirical_ev_r`, `ev_drift_r`
     - `total_pnl_usd`, `annualised_return_pct`
     - `oos_sharpe`, `oos_win_rate`, `oos_trade_count`, `oos_penalty`
     - `confidence_rating`
     - `score`, `score_detail`
     - `direction`

2. **Detect strategy change**
   - Load `divisions/trading/packets/backtester.json` if it exists
   - Compare `active_strategy.strategy_id` with previous packet's `metrics.strategy_id`
   - If different: set `strategy_changed: true` and record previous strategy name
   - If same: set `strategy_changed: false`
   - If no previous packet: set `strategy_changed: null` (first run)

3. **Evaluate quality flags**
   Set the following flags based on thresholds:
   - `oos_weak`: true if `oos_sharpe` < 0.3 OR `oos_win_rate` < 0.35
   - `high_ev_drift`: true if `abs(ev_drift_r)` > 0.1
   - `low_confidence`: true if `confidence_rating` is "Low" or "Very Low"
   - `poor_drawdown`: true if `max_drawdown` > 0.05 (5%)
   - `healthy`: true only if none of the above flags are set

4. **Determine escalation**
   Escalate (`escalate: true`) if ANY of the following are true:
   - `strategy_changed: true` — new strategy selected this cycle
   - `oos_weak: true` — out-of-sample validation is failing
   - `high_ev_drift: true` — theoretical vs empirical EV diverging significantly
   - `low_confidence: true` AND `strategy_changed: true` — new strategy with low confidence

   Do NOT escalate for:
   - `low_confidence` alone (common, not actionable without strategy change)
   - `poor_drawdown` alone unless combined with `oos_weak`

5. **Build escalation reason string**
   If escalating, compose a concise reason. Examples:
   - "Strategy changed: {prev_name} → {new_name} (cycle {n})"
   - "OOS validation weak: Sharpe {oos_sharpe}, Win Rate {oos_win_rate}"
   - "High EV drift detected: theoretical {theoretical_ev_r} vs empirical {empirical_ev_r}"

6. **Compose summary string**
   Format:
   ```
   Cycle {n} | Strategy: {strategy_name} | Sharpe: {sharpe} | Win Rate: {win_rate%} | OOS: {oos_sharpe} | Confidence: {confidence_rating}
   ```
   If strategy changed, prefix with: "[NEW STRATEGY] "

7. **Write executive packet**
   Write to `divisions/trading/packets/backtester.json`:
   ```json
   {
     "division": "trading",
     "generated_at": "<ISO timestamp>",
     "skill": "backtester",
     "status": "success | partial | failed",
     "summary": "<composed summary string>",
     "action_items": [],
     "metrics": {
       "cycle_number": 0,
       "strategy_id": "",
       "strategy_name": "",
       "strategy_changed": null,
       "prev_strategy_name": null,
       "direction": "long | short | both",
       "sharpe": null,
       "sortino": null,
       "win_rate": null,
       "profit_factor": null,
       "max_drawdown": null,
       "avg_r": null,
       "rr_ratio": null,
       "theoretical_ev_r": null,
       "empirical_ev_r": null,
       "ev_drift_r": null,
       "total_pnl_usd": null,
       "annualised_return_pct": null,
       "oos_sharpe": null,
       "oos_win_rate": null,
       "oos_trade_count": null,
       "oos_penalty": null,
       "confidence_rating": "",
       "score": null,
       "quality_flags": {
         "oos_weak": false,
         "high_ev_drift": false,
         "low_confidence": false,
         "poor_drawdown": false,
         "healthy": true
       }
     },
     "artifact_refs": [],
     "escalate": false,
     "escalation_reason": "",
     "task_id": "",
     "confidence": null,
     "urgency": "normal",
     "recommended_action": "",
     "approval_required": false,
     "approval_status": ""
   }
   ```

## Error Handling
- `spx500_cycle_state.json` missing: `status: partial`, summary "agent-network cycle state not found — backtester did not run", `escalate: false`
- File exists but `active_strategy` is null or missing: `status: partial`, summary "cycle state present but no active strategy found"
- JSON parse error: `status: failed`, include raw error message in summary, `escalate: true`
- Never fabricate strategy metrics
- On any error, still write a packet (partial or failed) — never leave the packet stale from a previous run without updating `generated_at`
