---
name: releasing
description: >-
  Cut a clean version release the right way: pick the next semantic version,
  bump the beta/dev version, generate a changelog from git history, and (only on
  explicit request) tag a stable release. Use when the user says "cut a release",
  "make a stable release", "bump the version", "increment beta", "tag vX.Y.Z",
  "what should the next version be", "release this", "ship a release", "write the
  release notes", or "the preflight won't let me cut this stable". Honors
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
2. Choose the stable number: the current beta minus its pre-release suffix (or
   the number the user names). Stable is what the beta validated — never a
   number no beta ever ran.
3. **Preflight** — run the deterministic gate before tagging:
   ```
   python ${CLAUDE_SKILL_DIR}/scripts/release_preflight.py --stable vX.Y.Z \
       [--feature-justification "<the user-facing wave this ships>"] \
       [--breaking-justification "<what breaks>"] [--allow-same-day "<reason>"] \
       [--version-file VERSION|package.json|pyproject.toml]
   ```
   It checks version file == stable, the `vX.Y.Z` format, one stable per day,
   bump-class paperwork (a minor needs a written feature justification, a major a
   breaking one), and number burning. Exit 2 = do not tag. Paperwork failures
   are cleared by writing the honest reason; blocking failures are not.
4. **Release notes** from the last tag (see "Release notes people can read"):
   `git log --oneline <last-tag>..HEAD`, then write them for a user, not a
   reviewer. Keep them in the repo (e.g. `docs/release-notes-vX.Y.Z.md`).
5. Create an **annotated** tag and push it:
   ```
   git tag -a vX.Y.Z -m "<project> vX.Y.Z - <summary>"
   git push origin vX.Y.Z
   ```
   and, where the project publishes GitHub releases,
   `gh release create vX.Y.Z --title "<project> vX.Y.Z - <summary>" --notes-file <notes>`.
6. **Advance the beta** past the tag (e.g. tagged `v2.5.3` -> set version to
   `2.5.4-beta`) and commit, so beta resumes ahead of stable.
7. **Verify, then get it reviewed.** `git ls-remote --tags origin vX.Y.Z` shows
   the tag; `gh release view vX.Y.Z` shows it published (not draft or
   prerelease, unless intended); the version file is on the next beta; any
   "latest stable" link resolves. Then have a reviewer in a different context
   re-check the tag, the notes against the commit range, and the beta bump
   before you report the release as done.

### Catch-up stables (several betas at once)

In a continuous-beta repo where stable is cut only on request, one stable often
covers several minors (`v11.1.0 -> v11.4.3`). A naive anti-burn rule ("advance
at most one minor") plus "stable == beta" is then **unsatisfiable**: no number
passes and every cut needs an override flag — and an override needed on the
normal path is a broken default that trains everyone to pass it blindly.

Make the guard evidence-based instead: every beta bump is a committed change to
the version file, so its git history records which levels the beta actually
ran. A catch-up passes when the walk from the last stable to the target moves
one level at a time and the beta held every level on the way (the preflight
reads this from `git log -p -- <version file>`). Jumping to a minor or major no
beta ever ran is still number burning and still fails. The catch-up still pays
its paperwork: a minor-class catch-up needs `--feature-justification` naming the
features it ships. Keep a raw override (`--allow-catchup "<reason>"`) only for
a repo whose version history cannot be read (shallow clone, rewritten history);
needing it on a normal cut is a bug to report.

## Release notes people can read

Notes are for the person using the software, not for the reviewer of the diff.

- **Lead with the effect.** "The portfolio card refreshes itself when its data
  is old" — not "TKT-123: add auto-refresh hook". Ticket ids and commit hashes
  go in parentheses at most, never as the headline.
- **Sections:** New / Fixed / (Privacy or Security, when relevant) /
  Housekeeping / **Known issues**. Known issues are honest: name what is still
  broken or unverified and what the user should do about it.
- **Cumulative.** A catch-up stable describes everything since the *previous
  stable*, across every beta in between; a hotfix's notes carry the whole
  minor line so far, so the latest release page is complete on its own.
- **Title** `<project> vX.Y.Z — <short summary of the headline changes>`;
  keep the prefix consistent across releases.
- **No point-in-time trivia** a reader can't use (internal counts, test
  totals); put those in the release commit or the tracker.

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
- **Make the bump class deterministic.** Left to judgment, an autopilot always
  picks patch: one repo sat on the same minor through ~19 patch bumps while whole
  new pages and subsystems shipped. Decide it from the diff instead — a wave that
  adds a new page/screen or registers a new API endpoint is a **minor**,
  anything else a patch — and have the bump script pick it.
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
