---
name: repo-monitor
description: Scan Matthew's GitHub repositories every 3 hours using the gh CLI. Flag TODOs, FIXMEs, stale branches, frequent edits, missing READMEs, and potential issues. Save digest to reports/ and send to Telegram at 3PM.
schedule: every 3 hours
division: dev-automation
---

## Trigger
Runs every 3 hours on schedule. The 3PM run triggers the Telegram send.

## Prerequisites
- GitHub CLI (`gh`) must be authenticated — run `gh auth status` to verify
- If not authenticated: surface error to Telegram immediately, abort run

## Steps

1. **Verify auth**
   ```bash
   gh auth status
   ```
   If not authenticated: send Telegram alert and stop. Do not proceed.

2. **List repositories**
   ```bash
   gh repo list --limit 100 --json name,url,updatedAt,defaultBranchRef
   ```

3. **For each repository, run the following checks:**

   **a. TODO / FIXME scan**
   ```bash
   gh api repos/{owner}/{repo}/git/trees/HEAD?recursive=1
   # then fetch and grep source files for TODO, FIXME, HACK, XXX
   ```
   Record: file path, line number, comment text

   **b. Stale branch check**
   ```bash
   gh api repos/{owner}/{repo}/branches
   ```
   Flag branches with last commit older than 14 days that are not `main` or `master`

   **c. Commit frequency**
   Check commits in the last 7 days. Flag repos with 0 commits as potentially stale.

   **d. Missing README**
   Check if README.md exists at repo root. Flag if missing.

   **e. Architectural issues** (heuristic flags)
   - Files over 500 lines
   - Functions with high cyclomatic complexity (if detectable)
   - Repeated similar filenames suggesting duplication

4. **Compile digest**
   Structure:
   ```
   ## Repo Monitor Digest — {date}

   ### {repo-name}
   - TODOs: {count} found → {file}:{line}
   - Stale branches: {branch names}
   - Last commit: {date}
   - README: MISSING | OK
   - Flags: {list of issues}
   ```

5. **Save digest**
   Write to `reports/repo-digest-{YYYY-MM-DD}.md`

6. **Send to Telegram** (3PM run only)
   Summarize: total repos scanned, total issues found, top 3 priority items.
   Attach or link full digest.

## Output
- `reports/repo-digest-{date}.md`
- Telegram message at 3PM with digest summary

## Error Handling
- If gh auth fails: Telegram alert "repo-monitor: gh not authenticated — skipping run"
- If a single repo scan fails: log error, continue with other repos
- If all repos fail: Telegram alert with error details
- Never silently fail — every error must be surfaced
