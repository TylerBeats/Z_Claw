---
name: health-logger
description: Prompt Matthew on Telegram at 6PM daily to collect health and lifestyle data. Save structured entries to state/health-log.json for use by the performance correlation agent.
schedule: daily 18:00
division: personal
---

## Trigger
Runs daily at 18:00 (6PM). Sends prompt to Matthew via Telegram and collects his responses.

## Steps

1. **Send opening prompt to Telegram**
   ```
   J_Claw // Daily Health Check-In — {date}

   Reply with your data for today:
   1. Food: what did you eat and when?
   2. Hydration: approx. water intake?
   3. Adderall: dose + time taken
   4. Exercise: type + duration (or "none")
   5. Sleep: hours last night + quality (1-10)

   Reply "skip" to mark today as no data.
   ```

2. **Wait for response** (30-minute window)
   - If no response in 30 minutes: send a single reminder
   - If no response in 2 hours from initial prompt: mark entry as skipped

3. **Parse response**
   Extract from Matthew's natural-language reply:
   - `food`: array of meals with approximate times
   - `hydration`: string (e.g., "2L", "not much")
   - `adderall_dose`: string (e.g., "20mg")
   - `adderall_time`: string (e.g., "9am")
   - `exercise_type`: string (e.g., "30min walk", "none")
   - `exercise_duration_min`: number or null
   - `sleep_hours`: number
   - `sleep_quality`: number 1–10

4. **Validate completeness**
   - Required fields: sleep_hours, sleep_quality
   - If critical fields are missing: ask a targeted follow-up (one message only)

5. **Save entry to state**
   Write to: `C:\Users\Matty\OpenClaw-Orchestrator\state\health-log.json`
   - Read the existing file
   - Append a new entry to the `entries` array
   - Update the `last_logged` field to current ISO timestamp
   - Write the full updated JSON back to the file

   Entry schema:
   ```json
   {
     "date": "YYYY-MM-DD",
     "logged_at": "<ISO timestamp>",
     "skipped": false,
     "food": [],
     "hydration": "",
     "adderall_dose": "",
     "adderall_time": "",
     "exercise_type": "",
     "exercise_duration_min": null,
     "sleep_hours": null,
     "sleep_quality": null
   }
   ```

   DO NOT save a .txt file. DO NOT save to the workspace folder.
   The only valid output is the JSON file at the path above.

6. **Confirm to Matthew**
   ```
   Logged. See you tomorrow at 6PM.
   ```

## Output
- Appended entry in `C:\Users\Matty\OpenClaw-Orchestrator\state\health-log.json`
- Confirmation message via Telegram
- No other files created — no .txt, no workspace files

## Error Handling
- If Telegram send fails: log error and retry after 5 minutes (max 3 retries)
- If response is "skip": log entry with `skipped: true`, all fields null
- If Matthew is unresponsive for 2 hours: log as skipped, note in logs
- Never send multiple reminders — one follow-up only
