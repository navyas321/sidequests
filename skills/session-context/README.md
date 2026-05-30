# session-context

A Claude Code skill for session, state, and context continuity — so a
brand-new agent session picks up exactly where the last one left off, in any
repo, any tech stack.

## What it does

| Flow | Trigger phrases | Effect |
|------|----------------|--------|
| **Orient** | "resume where I left off", "where are we", "orient yourself", "what's next", "what did we do last time" | Reads `docs/STATUS.md`, `CLAUDE.md`, git log, and open PRs; prints a tight summary of current phase + exact next step. Read-only. |
| **Checkpoint** | "checkpoint", "save session state", "update STATUS", "wrap up" | Writes/overwrites `docs/STATUS.md` with phase, what this session did, the exact next step, decisions, and key files. Appends a dated one-line entry to `docs/SESSION_LOG.md`. |

## Files used

| File | Purpose |
|------|---------|
| `docs/STATUS.md` | Single-source project snapshot — overwritten each checkpoint. |
| `docs/SESSION_LOG.md` | Append-only dated one-liners (one per session). |
| `CLAUDE.md` (repo root) | Project conventions read by orient; never modified by this skill. |

## Helper script

`scripts/snapshot.sh` — portable bash; gathers branch, `git log --oneline -15`,
`git status -s`, and `gh pr list --state open` (degrades gracefully if `gh` is
absent). Prints a ready-to-paste STATUS.md `## Snapshot` section.

```bash
# Run from inside the repo:
bash /path/to/skills/session-context/scripts/snapshot.sh

# Or pass the repo dir explicitly:
bash /path/to/skills/session-context/scripts/snapshot.sh /path/to/myrepo
```

## Installation (via sidequests plugin)

The skill ships as part of the
[sidequests](https://github.com/navyas321/sidequests) Claude Code plugin. Once
the plugin is installed and enabled, invoke it with:

```
/sidequests:session-context orient
/sidequests:session-context checkpoint
```

## docs/STATUS.md shape

```markdown
# Project Status

**Last updated:** YYYY-MM-DD

## Phase
<current phase or milestone>

## This session did
- <item>

## Next step
<single actionable sentence>

## Open decisions / blockers
- <item>

## Key files
- `<path>` — <role>

## Snapshot (auto)
<!-- updated by snapshot.sh -->
<branch, log, status, open PRs>
```

## License

MIT — part of [sidequests](https://github.com/navyas321/sidequests).
