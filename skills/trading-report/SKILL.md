---
name: trading-report
description: Collect daily trading session data from the MT5 system, format a structured performance summary, save to state/trade-log.json, and send to Matthew via Telegram at 6PM.
schedule: daily 18:00
division: trading
---

## Trigger
Runs daily at 18:00 (6PM). Also runs after each manual session when Matthew invokes the trade-tracker.

## Prerequisites
- MT5 trading system must be accessible
- If MT5 is unavailable: send Telegram alert and abort — do not fabricate data

## Steps

1. **Connect to MT5 system**
   - Use existing MT5 integration (do not redesign)
   - Pull today's closed trades and session data

2. **Parse trade records**
   For each trade, extract:
   ```json
   {
     "instrument": "",
     "direction": "long | short",
     "entry_price": null,
     "exit_price": null,
     "entry_time": "",
     "exit_time": "",
     "entry_reason": "",
     "exit_reason": "",
     "r_multiple": null,
     "result": "win | loss | breakeven",
     "session": "london | ny | asian | overlap",
     "rule_adherence": "yes | partial | no",
     "notes": ""
   }
   ```

3. **Calculate session stats**
   - Total trades today
   - Win rate (today)
   - Average R multiple
   - Best trade (instrument + R)
   - Worst trade (instrument + R)
   - Rule adherence rate (% of trades marked "yes")

4. **Save to state**
   Append session record to `state/trade-log.json`:
   ```json
   {
     "date": "YYYY-MM-DD",
     "logged_at": "<ISO timestamp>",
     "trades": [],
     "stats": {
       "total_trades": 0,
       "wins": 0,
       "losses": 0,
       "win_rate": null,
       "avg_r": null,
       "best_r": null,
       "worst_r": null,
       "rule_adherence_rate": null
     }
   }
   ```
   Update global `stats` (rolling totals).

5. **Format Telegram summary**
   ```
   J_Claw // Trading Report — {date}

   Trades: {total} | W/L: {wins}/{losses} | Win Rate: {win_rate}%
   Avg R: {avg_r} | Best: {best_instrument} +{best_r}R

   Rule Adherence: {adherence_rate}%

   {list each trade: instrument | direction | result | R}
   ```

6. **Send to Telegram**
   Also share session data with Personal Optimization division for correlation analysis.

## Output
- Updated `state/trade-log.json`
- Telegram summary message at 6PM

## Error Handling
- If MT5 unavailable: Telegram alert "trading-report: MT5 connection failed — manual entry required"
- If no trades today: send brief "No trades logged today." message — do not skip the send
- If Telegram fails: save report to `reports/trade-report-{date}.md` and retry
- Never fabricate or estimate trade data — only log what MT5 reports
