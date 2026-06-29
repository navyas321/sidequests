# usage-limit-guard

Keep a **repo-backed autonomous loop** (a backlog watcher, a `/loop`, a nightly
headless agent) making forward progress across Claude usage limits, outages, and
session death — and resume cleanly afterward.

The trick is simple: **the repo is the resume state, not the session.** Commit per
work-item, keep a tiny `CHECKPOINT.json` + a dated journal, and a brand-new session
resumes by *reading* that state. One kill loses at most the item in flight.

This is a generalization of a real backlog-watcher pattern into a reusable,
stack-agnostic recipe. `git` is the only hard requirement.

## What it gives you

- **Usage visibility** — the only programmatic usage signal is **local transcript
  token-burn** (scan `~/.claude/projects/**/*.jsonl`, sum `message.usage`). The real
  claude.ai **5h / weekly limit %** is *not* exposed by any API; the skill says so
  plainly and reports the burn proxy instead.
- **Limit guard** — run headless with `--output-format json`, detect the limit
  (there is **no dedicated rate-limit exit code yet** — branch on exit code +
  payload + a `session limit · resets <time>` string match), parse the reset time,
  and back off cleanly instead of dying mid-edit.
- **Durable resume** — commit-per-item + `CHECKPOINT.json`
  (`lastRun` / `lastItem` / `nextItem` / `doneThisCycle` / `limitResetsAt`) + a dated
  journal. A fresh session reads those + git log + memory and continues. **On Windows
  do NOT use `--resume` / `-c`** — they freeze / lose conversations / crash on killed
  sessions; resume is by reading repo state only.

## Use it when

You hear: *"won't this die on the 5-hour limit"*, *"make this survive usage
limits"*, *"resume after the limit resets"*, *"checkpoint so a fresh session can
continue"*, *"the watcher died and lost its work"*, *"run this headless overnight"*,
or *"how much usage am I burning"* — or whenever you're building/hardening any loop
that must survive limits and restarts.

## Layout

```
usage-limit-guard/
├── SKILL.md                  # the procedure (usage / guard / checkpoint / resume flows)
├── TOKEN-MANAGEMENT.md       # avoid the limit: opusplan, model/effort tiering, /compact, cache discipline
├── README.md                 # this file
└── scripts/
    ├── token_burn.py         # local token-burn report (today / 5h / 7d) — the only programmatic usage signal
    └── detect_limit.py       # classify a headless run as OK / LIMIT <reset> / ERROR <category>
```

## Quick start

```bash
# how much have I burned locally? (proxy for rolling-window pressure)
python scripts/token_burn.py

# in a headless loop: run one bounded item, then check if we hit the limit
claude -p "<do the next backlog item>" --output-format json --max-turns 30 > run.json; rc=$?
python scripts/detect_limit.py run.json $rc
#   OK            -> commit the item, advance CHECKPOINT.json, continue
#   LIMIT <time>  -> commit, write limitResetsAt, EXIT (next scheduled run resumes)
#   ERROR <cat>   -> log + back off per category
```

Both scripts are pure Python stdlib (no dependencies) and read-only against your
transcripts.

## How the limits work (June 2026, keep current)

- **5-hour rolling window**: opens on your first prompt, shared pool across Claude
  Code + chat + Cowork (5h cap doubled 2026-05-06).
- **Weekly cap**: resets at a fixed account-assigned time each week.
- **Hard stop** at the limit (extra-usage off) until the window resets; the message
  states the reset time.
- **Since 2026-06-15** non-interactive usage (`claude -p`, Agent SDK, GitHub
  Actions) draws from a *separate monthly credit pool* — so a headless loop may
  exhaust credits rather than the 5h/weekly caps. The guard treats both as "the
  limit".

See `SKILL.md` for the full procedure and the setup checklist for bootstrapping the
pattern in a new repo.

## License

MIT (see repo root `LICENSE`).
