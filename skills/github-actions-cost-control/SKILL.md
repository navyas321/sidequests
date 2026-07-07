---
name: github-actions-cost-control
description: Diagnose and stop GitHub Actions free-tier minute burn (2,000 min/mo) across an account — find the biggest burners (paused-project crons, macOS 10x runners, burst-commit CI) and fix them. Use when you get a "used 100% of Actions minutes" email or want to audit CI spend.
---

# GitHub Actions cost control

The free tier is **2,000 Actions minutes/month, account-wide** (all repos share it), and **macOS runners bill 10×** (1 macOS min = 10 quota min; Windows = 2×; Linux = 1×). A "100% used" email means any further usage bills real money unless a $0 budget is set.

## 1. Audit — find the burners (in impact order)

```bash
# every workflow across every repo + its state (find active ones on dormant projects)
for repo in $(gh repo list <owner> --limit 100 --json name --jq '.[].name'); do
  gh api "repos/<owner>/$repo/actions/workflows" \
    --jq ".workflows[] | select(.state==\"active\") | \"$repo: \(.name) [\(.path)]\""
done

# per suspect repo: recent run frequency (a weekly/hourly cron shows a regular cadence)
gh api "repos/<owner>/<repo>/actions/runs?per_page=30" \
  --jq '.workflow_runs[] | "\(.name)\t\(.created_at)"'

# check a workflow's trigger + runner OS (cron? macos = 10x?)
gh api "repos/<owner>/<repo>/contents/.github/workflows/<file>.yml" --jq '.content' \
  | base64 -d | grep -iE "cron|schedule|on:|runs-on|macos|self-hosted"
```

Red flags, worst first:
- **Active workflows on a PAUSED/dormant project** — especially `schedule:`/cron (fires forever regardless of activity) and anything on `macos-*` (10×). This is usually the #1 burner.
- **CI that stacks a full run per commit** when a fleet/automation pushes in bursts (no `concurrency`).
- **Per-push CI on a data-committing repo** (a backlog/journal/cache auto-commit triggers CI for zero code value).
- **Chronically-red workflows** — waste minutes twice.

## 2. Fix (highest leverage first)

```bash
# Disable every workflow on a paused project (reversible: gh workflow enable <id>)
gh api -X PUT "repos/<owner>/<repo>/actions/workflows/<id>/disable"
```

Add to any CI a fleet pushes to in bursts — collapses a burst to ~1 billed run:
```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

Skip CI on data-only automation commits:
```yaml
on:
  push: { branches: [main], paths-ignore: ['data/**','docs/**','**/*.md','.gitignore'] }
```

Put `[skip ci]` in the commit message for a CI-config/docs-only change while near the cap.

## 3. Alternatives to hosted minutes

- **Self-hosted runner** on your own host (`runs-on: [self-hosted, <label>]`) — **free, unlimited**. The durable fix for a repo with heavy or frequent CI.
- **Local pre-commit gate** — if agents already run the test suite locally before every commit (e.g. `scripts/smoke-test.py`), hosted CI is belt-and-suspenders; you can make it PR-only or drop it.
- **$0 Actions spending budget** (Settings → Billing → spending limit) — blocks all overage billing until reset. Safe when a local gate is the real guard. Blocks hosted CI until the cycle rolls over.

## Rule of thumb
macOS + cron + dormant-project = the money pit. Disable dormant-project workflows first, add `concurrency` to burst-pushed CI, keep real quality gates local, and reserve hosted minutes for PRs that actually need a clean-room build.
