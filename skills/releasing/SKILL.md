---
name: releasing
description: >-
  Cut a clean version release the right way: pick the next semantic version,
  bump the beta/dev version, generate a changelog from git history, and (only on
  explicit request) tag a stable release. Use when the user says "cut a release",
  "make a stable release", "bump the version", "increment beta", "tag vX.Y.Z",
  "what should the next version be", "release this", or "ship a release". Honors
  a continuous-beta / tag-cut-stable model where beta always runs ahead of
  stable. Project-agnostic; works in any git repo. Reads the repo's own
  RELEASING.md / docs if present and follows it over these defaults.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: "[patch|minor|major | stable | vX.Y.Z]"
---

# releasing

A disciplined, low-risk release flow for any repo. **If the repo has its own
`RELEASING.md`, `docs/RELEASING.md`, `CONTRIBUTING`, or a versioning section in
`CLAUDE.md`/`README`, read it first and follow it — it overrides these defaults.**
(In life-in-tabs, the concrete runbook is `docs/RELEASING.md`.)

## Core model: continuous beta, tag-cut stable

- The live **beta/dev version** moves forward continuously and stays AHEAD of
  stable. It lives wherever the project keeps it: a `VERSION` file, `package.json`
  `version`, `pyproject.toml`, `__version__`, etc. Detect it, don't assume.
- **Stable is a git tag** (`vX.Y.Z`, annotated). Cutting stable is a deliberate,
  usually human-gated action — do NOT tag stable unless the user explicitly asks.
- After tagging stable, immediately advance the beta so it's ahead again.

## Pick the next version (SemVer)

| bump | when |
|------|------|
| **patch** `z` | bug fixes, copy/UI tweaks, a routine maintenance wave |
| **minor** `y` | a new user-facing feature / endpoint / page |
| **major** `x` | a breaking change or a full redesign |

If unsure, inspect what changed since the last tag and infer:
`git log --oneline "$(git tag --sort=-creatordate | head -1)"..HEAD`.

## Flow A — bump the beta (the common case)

1. **Green first.** Run the project's test/smoke gate (e.g.
   `python scripts/smoke-test.py`, `npm test`). Never release a red tree.
2. **Find + edit the version source** to the next `x.y.z` beta/dev value
   (keep the project's suffix convention, e.g. `-beta`, `-dev`, `-rc`). Use the
   project's IO conventions (encoding, atomic writes).
3. **Commit** with the project's commit identity and a `release: vX.Y.Z-beta`
   message, then push.

## Flow B — cut a stable tag (only on explicit request)

1. Green test/smoke gate — mandatory.
2. Choose the stable number (usually current beta minus its pre-release suffix,
   or the number the user names).
3. **Changelog** from the last tag:
   `git log --oneline <last-tag>..HEAD` -> summarize notable items into notes.
4. Create an **annotated** tag and push it:
   ```
   git tag -a vX.Y.Z -m "<project> vX.Y.Z - <summary>"
   git push origin vX.Y.Z
   ```
   (or `gh release create vX.Y.Z --notes-file NOTES.md` for a GitHub release.)
5. **Advance the beta** past the tag (e.g. tagged `v2.5.3` -> set version to
   `2.5.4-beta`) and commit, so beta resumes ahead of stable.

## Guardrails

- Never tag stable without explicit user go-ahead.
- Never release on a red test/smoke run — fix or revert first.
- Keep beta strictly ahead of stable at all times.
- Use the repo's commit identity and IO/atomic-write conventions.
- Prefer annotated tags (`-a`) so the tag carries a message/changelog.

## Quick commands

```
# detect current version source (pick what exists):
cat VERSION 2>/dev/null; grep -m1 '"version"' package.json 2>/dev/null; grep -m1 version pyproject.toml 2>/dev/null
# latest stable tag:
git tag --sort=-creatordate | head -1
# unreleased changes since last stable:
git log --oneline "$(git tag --sort=-creatordate | head -1)"..HEAD
```

## Release cadence & enforcement (don't let releases lapse)

Cutting releases is not only an on-request action — it is a **cadence** the agent
must keep, or shipped work goes un-versioned and un-rollback-able. Real failure
mode this guards against: a repo accumulated **782 commits / 190 items since the
last stable tag** before anyone noticed.

- **Bump the beta every shipped wave** — treat it as part of the wave's
  Definition of Done, right after the smoke-green commit (patch for a
  fixes/quality wave, minor when a feature/endpoint landed). Never leave the beta
  `VERSION` stale while dozens of commits pile up.
- **Proactively cut stable at milestones.** When unreleased work since the last
  tag gets large (rule of thumb: **>~30 items, or a redesign/architecture/breaking
  change landing**), surface it and — with user go-ahead (stable stays
  human-gated) — cut the tag. Don't wait to be asked every time; *suggest* it.
- **On session resume, check the gap:**
  `git log "$(git tag --sort=-creatordate | head -1)"..HEAD --oneline | wc -l`.
  A large number with no recent tag = flag a release before continuing.
- After any stable tag, immediately advance the beta so it's ahead again.

The point: **beta moves every wave; stable is cut at milestones, proactively —
not only when the user finally notices the version is stale.**
