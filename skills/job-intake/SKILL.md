---
name: job-intake
description: Fetch job listings every 3 hours from free APIs and RSS feeds, normalize to standard schema, deduplicate against previously seen jobs, and pass new listings to hard-filter.
schedule: every 3 hours
division: opportunity
---

## Trigger
Runs every 3 hours on schedule. Also runs on manual invocation from Matthew.

## Sources

| Source | Type | URL | Auth | Status |
|---|---|---|---|---|
| We Work Remotely | RSS | `https://weworkremotely.com/remote-jobs.rss` | None | ✅ Live |
| Remote OK | REST API | `https://remoteok.com/api` | None | ✅ Live |
| Remotive | REST API | `https://remotive.com/api/remote-jobs` | None | ✅ Live (use if no rate limit) |
| Web3.career | RSS | ~~https://web3.career/rss~~ | — | ❌ Dead (500/404) |
| CryptoJobsList | RSS | ~~https://cryptojobslist.com/rss~~ | — | ❌ Blocked (403) |
| Remote.co | RSS | ~~https://remote.co/remote-jobs/developer/feed/~~ | — | ❌ Timeout |

Do NOT attempt to scrape LinkedIn, Indeed, or any job board that requires login.
Web3.career, CryptoJobsList, and Remote.co feeds are confirmed dead/blocked as of 2026-03-17 — skip them entirely until further notice.

## Fetch Methods

### We Work Remotely (RSS)
```
GET https://weworkremotely.com/remote-jobs.rss
```
Returns XML. Parse each `<item>`. Use `<link>` as unique job ID.
Fields: `<title>`, `<link>`, `<description>`, `<pubDate>`, `<region>`.

### Remote OK (REST API)
```
GET https://remoteok.com/api
```
Returns JSON array. First element is metadata — skip it, parse from index 1.
Fields: id, url, title, company, location, salary_min, salary_max, tags, date.

### Remotive (REST API — use only if no rate limit this session)
```
GET https://remotive.com/api/remote-jobs
```
Returns JSON array. Fields: id, url, title, company_name, candidate_required_location, salary, description, job_type, tags, publication_date.

## Steps

1. **Pre-flight: API budget check**
   - If you have received any rate limit error in this session: skip Remotive API entirely, use RSS feeds only
   - If all sources previously failed in this session: notify Matthew once via Telegram and abort — do not retry
   - Prefer RSS sources at all times — they are zero-cost and have no quotas
   - Remotive API is a bonus source only, not required

3. **Load seen jobs**
   - Read `C:\Users\Matty\OpenClaw-Orchestrator\state\jobs-seen.json`
   - Build a set of seen job IDs using composite key: `source + job_id`

4. **Fetch listings per source**
   - For each source: fetch using the method above
   - If a source fetch fails: log the error, continue to next source
   - Never abort the full run due to a single source failure

5. **Normalize each listing** to standard schema:
   ```json
   {
     "id": "<source>-<job_id>",
     "title": "",
     "company": "",
     "location": "",
     "remote": true,
     "pay_min": null,
     "pay_max": null,
     "pay_type": "hourly | salary | unspecified",
     "description_summary": "",
     "url": "",
     "source": "",
     "fetched_at": "<ISO timestamp>",
     "seen": false,
     "filtered": false,
     "tier": null
   }
   ```
   - Extract pay from salary field or description where possible
   - If location is empty or "worldwide", set `remote: true`

6. **Deduplicate**
   - Compare each listing against the seen set by composite ID
   - Skip any job already seen — never re-surface it
   - Only new jobs proceed

7. **Update state**
   - Read `C:\Users\Matty\OpenClaw-Orchestrator\state\jobs-seen.json`
   - Append new listings to `jobs` array
   - Update `last_run` to current ISO timestamp
   - Increment `total_seen` by count of new listings
   - Write updated JSON back to the file

8. **Handoff**
   - Pass new listings array to hard-filter skill

## Output
- Updated `C:\Users\Matty\OpenClaw-Orchestrator\state\jobs-seen.json`
- New listings array passed to hard-filter

## Error Handling
- Per-source failure: log to `C:\Users\Matty\OpenClaw-Orchestrator\logs\job-intake-errors.log`, continue
- If ALL sources fail: send Telegram alert — "job-intake: all sources failed at {timestamp}"
- If state file is missing: create it with empty schema `{ "jobs": [], "last_run": null, "total_seen": 0 }`
- Never skip deduplication under any circumstances
