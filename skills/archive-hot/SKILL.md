---
name: archive-hot
description: Archive stale market scan files from the hot cache into dated cold archives. Enforces the 24-hour TTL and 256MB hot cache size limit. Run by division-chief-trading at 18:00 daily as part of the checkpoint archive step.
schedule: daily 18:00
division: trading
runner: division-chief-trading
---

## Trigger
Called by division-chief-trading at 18:00 daily, as part of the checkpoint archive sequence.
Runs AFTER trading-report and backtester complete.
Do NOT call Claude directly — this skill runs under the local GGUF division orchestrator.

## Purpose
The hot cache (`divisions/trading/hot/`) is a 24-hour rolling window. Market scan files
accumulate hourly and must be archived daily to keep the hot directory clean and bounded.

This skill handles the market scan files specifically. Trade session bundles are handled
separately by the trading-report skill via artifact-manager.

## Prerequisites
- `divisions/trading/hot/` must exist (always true if market-scan has run)
- `divisions/trading/cold/` must exist — create it if missing
- `divisions/trading/manifests/` must exist — create it if missing

## Steps

1. **Scan hot directory**
   - Read all files in `divisions/trading/hot/`
   - Filter to market scan files matching pattern: `market-YYYYMMDD-HHMM.json`
   - Parse the date from each filename (format: `market-{YYYYMMDD}-{HHMM}.json`)
   - Determine file age: compare parsed date to `now - 24 hours`
   - Separate into two lists:
     - `stale`: files where parsed date < `now - 24 hours`
     - `current`: files where parsed date >= `now - 24 hours`

2. **Skip if nothing to archive**
   - If `stale` list is empty: log "No stale market scans to archive", proceed to size check (step 5)

3. **Group stale files by date**
   - Group each stale file by its parsed calendar date (YYYY-MM-DD)
   - Example: all `market-20260320-*.json` files → group `2026-03-20`

4. **Archive each date group**
   For each date group:
   a. Determine archive path: `divisions/trading/cold/market-scans-{YYYY-MM-DD}.zip`
   b. Check if archive already exists for this date
      - If yes: open existing archive and append new files
      - If no: create new zip archive
   c. Add all files in the group to the zip archive
   d. Verify archive integrity (file count in zip matches input count)
   e. Write or update manifest at `divisions/trading/manifests/market-scans-{YYYY-MM-DD}.manifest.json`:
      ```json
      {
        "bundle_id": "market-scans-{YYYY-MM-DD}",
        "division": "trading",
        "created_at": "<ISO timestamp>",
        "last_updated": "<ISO timestamp>",
        "date": "YYYY-MM-DD",
        "file_count": 0,
        "files": ["market-YYYYMMDD-HHMM.json", "..."],
        "tags": ["market-scan", "hot-archive"],
        "sensitivity": "internal",
        "ttl_hours": null,
        "extraction_hints": "Daily market scan snapshots. Each file contains price data for BTC, ETH, BNB, SOL and any signals triggered."
      }
      ```
   f. ONLY after successful archive + integrity check: delete the stale files from `hot/`
   g. Log: "Archived {n} files for {date} → cold/market-scans-{date}.zip"

5. **Enforce hot cache size limit**
   - Calculate total size of all files in `divisions/trading/hot/`
   - If total size > 256MB:
     - Identify oldest market scan files (by filename date) that are NOT in `current` list
     - Delete oldest files until total size is under 256MB
     - Log each deletion with filename and size
     - If still over 256MB after deleting all non-current files: escalate with reason "Hot cache exceeds 256MB limit even after archiving stale files"

6. **Return results to division chief**
   Division chief logs the archive result. No executive packet is written by this skill —
   archive activity is noted in the division chief's daily summary.
   Return:
   ```json
   {
     "status": "success | partial | failed",
     "archived_count": 0,
     "archived_dates": [],
     "deleted_from_hot": 0,
     "hot_size_mb_after": 0.0,
     "size_limit_enforced": false,
     "errors": []
   }
   ```

## Error Handling
- Zip creation fails (disk full, permission error): skip that date group, add to `errors[]`, continue with other groups — never leave partially zipped files without cleanup
- File deletion fails after successful archive: log warning, continue — stale file staying in hot is preferable to losing archive integrity
- Manifest write fails: log warning, continue — missing manifest is recoverable; missing archive is not
- Hot directory missing: return `status: failed`, reason "hot directory not found"
- Never delete files from hot/ without first confirming the archive exists and passes integrity check
- Never silently skip files — all skips must be logged with reason
