---
name: job-intake
description: Fetch job listings every 3 hours from free APIs and RSS feeds, normalize to standard schema, deduplicate against previously seen jobs, and pass new listings to hard-filter.
schedule: every 3 hours
division: opportunity
---

## Trigger
Runs every 3 hours on schedule. Also runs on manual invocation from Matthew.

## Sources

| Source | Type | URL | Auth |
|---|---|---|---|
| Remotive | REST API | `https://remotive.com/api/remote-jobs` | None |
| We Work Remotely | RSS | `https://weworkremotely.com/remote-jobs.rss` | None |
| Web3.career | RSS | `https://web3.career/rss` | None |
| CryptoJobsList | RSS | `https://cryptojobslist.com/rss` | None |
| Remote.co (dev) | RSS | `https://remote.co/remote-jobs/developer/feed/` | None |

Do NOT attempt to scrape LinkedIn, Indeed, or any job board that requires login.
All sources above are free, public, and do not require authentication.

## Fetch Methods

### Remotive (REST API)
```
GET https://remotive.com/api/remote-jobs
```
Returns JSON array of job objects. Fields: id, url, title, company_name, candidate_required_location, salary, description, job_type, tags, publication_date.

### RSS Sources (Web3.career, CryptoJobsList, Remote.co, We Work Remotely)
Fetch the RSS feed URL as XML. Parse each `<item>` element.
Standard RSS fields: `<title>`, `<link>`, `<description>`, `<pubDate>`, `<guid>`.
Use `<guid>` or `<link>` as the unique job ID.

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
