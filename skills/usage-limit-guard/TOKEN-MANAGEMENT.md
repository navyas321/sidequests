# TOKEN-MANAGEMENT.md — stretch a session, don't hit the 5h/weekly cap

Companion to `SKILL.md`. The guard catches the limit *after* you hit it; this file
is about **not hitting it** — burning fewer tokens per unit of work so a Max-plan
5-hour rolling block (and the weekly cap) lasts far longer.

Sourced from official Anthropic docs (June 2026): code.claude.com/docs `model-config`,
`costs`, `sub-agents`, `prompt-caching`. Verify against current docs over time — the
mechanics below are versioned and change.

> **One-line rule of thumb:** *plan on Opus, execute on Sonnet, fan out on Haiku;
> pick model + effort ONCE at the top of a session; `/compact` at task boundaries,
> `/clear` between unrelated tasks; never re-read what's already in context.*

---

## 0. Why model choice dominates the bill

> "Opus costs several times more per turn than Sonnet, and Sonnet more than Haiku."
> — Claude Code docs.

Roughly: **Opus ≈ 5× Sonnet** per token; **Haiku ≈ 15× cheaper than Opus**. The
single biggest lever on how fast you drain the 5h window is **which model is doing
each turn**. Everything else (context discipline, caching) is secondary but
compounding. On Max the default model is **Opus 4.8** — so by default you are
burning at the most expensive rate unless you tier down.

The weekly cap on Max has **two** sub-limits: one across all models and one for
**Sonnet-only**. Pushing routine work to Sonnet/Haiku spends the cheaper pools and
preserves the all-models (Opus) headroom for the hard stuff.

---

## 1. `/opusplan` — plan with Opus, execute with Sonnet (the headline win)

`opusplan` is a model alias (`/model opusplan`). Official behavior:

- **In plan mode** → uses **Opus** for reasoning / architecture decisions.
- **In execution mode** → automatically switches to **Sonnet** for code generation.
- Switching the model does **not** clear the conversation — Sonnet still sees the
  plan Opus produced. You only pay Opus rates during planning.

**Why it saves so much:** execution (writing many files, running edits, iterating)
is the token-heavy phase. Routing that through Sonnet instead of Opus is the
~5× saving applied to the *bulk* of the work. Practical framing from the field: a
session that would hit the wall after ~10 Opus-generated files can often do 40–50
through Sonnet before the same wall.

**Use it for:** refactors, feature builds, anything where you naturally plan first.
**Default recommendation for interactive dev sessions on Max: run `opusplan`,**
not raw `opus`.

**Caching caveat (important):** each plan↔execute toggle is a **model switch**, and
each model has its own cache — so every toggle triggers one slower, fully-uncached
turn. Net still a big win because Sonnet execution is far cheaper, but **don't
bounce in and out of plan mode repeatedly**; plan once, then execute.

If `availableModels` excludes Opus, `opusplan` just stays on Sonnet in plan mode
(graceful, no error).

---

## 2. `/model` tiering — match the model to the task

Default to the *cheapest model that can do the job*, switch up only when needed:

| Work type                                              | Model            |
| ------------------------------------------------------ | ---------------- |
| Hard reasoning, architecture, ambiguous root-causing   | **Opus** (or `opusplan` so execution drops to Sonnet) |
| Everyday coding, tests, well-specified implementation   | **Sonnet**       |
| Mechanical: file discovery, simple lookups, transforms, renames, log triage | **Haiku** |

- Start day-to-day sessions on **Sonnet**; escalate to Opus only when you genuinely
  need deep analysis. (`/model sonnet`, `/model opus`.)
- `/model` with no arg opens the picker; it now saves your choice as the default for
  new sessions. `--model <alias>` / `ANTHROPIC_MODEL` set it per-launch.
- **Pick the model at the START of the session.** A mid-session `/model` switch
  re-reads the entire conversation with **zero cache hits** (each model has its own
  cache) — one expensive uncached turn. `opusplan` is the sanctioned exception
  because the switch buys you cheap execution.

---

## 3. `/effort` tiering — cut thinking tokens on easy work

Extended thinking is **on by default at `high` effort** (Opus 4.8 / Sonnet 4.6).
Thinking tokens bill as **output tokens** and the default budget can be tens of
thousands per request — a large, often invisible, chunk of burn.

Levels: `low`, `medium`, `high`, `xhigh`, `max` (availability varies by model).

| Level    | When                                                                 |
| -------- | -------------------------------------------------------------------- |
| `low`    | Short, scoped, *not* intelligence-sensitive tasks (latency-sensitive)|
| `medium` | **Cost-sensitive work that can trade off a little intelligence — the go-to for routine/mechanical work** |
| `high`   | Default; balanced (most coding tasks)                                |
| `xhigh`  | Deeper reasoning, higher spend                                       |
| `max`    | Deepest; prone to overthinking — test before adopting broadly        |

- Set with `/effort <level>`, the slider in `/model`, `--effort`, or
  `effortLevel` in settings. `ultrathink` in a prompt requests deep reasoning for
  **one turn** without changing the session level.
- **Caching caveat:** effort level is part of the cache key — changing it mid-session
  also forces a full uncached turn (Claude Code confirms before applying). So, like
  model, **set effort once at the top of the session.**
- Rule: **routine/mechanical session → `medium`** (or `low` for trivial fan-out);
  **hard reasoning session → `high`/`xhigh`.** Don't pay `high` thinking on grunt work.

---

## 4. Subagent / fan-out tiering (the biggest hidden drain)

Subagents and agent teams each run their **own context window** — token usage scales
with how many you spawn and how long each runs. Subagent-heavy sessions can be the
majority of the bill. Two levers, both free wins:

**a) Tier the model per agent.** Subagent frontmatter / the Agent tool / Workflow
tasks accept a `model` field (`haiku` | `sonnet` | `opus` | `fable` | full ID |
`inherit`; default `inherit` = same as main = often Opus on Max). Set it explicitly:

```yaml
# in a subagent .md frontmatter
model: haiku      # file discovery, log triage, mechanical transforms
effort: low
---
# or for implementation workers
model: sonnet
effort: medium
```

> Official guidance: *"Control costs by routing tasks to faster, cheaper models like
> Haiku."* For agent teams: *"Use Sonnet for teammates."*

Override everything at once with `CLAUDE_CODE_SUBAGENT_MODEL=haiku` (or `sonnet`)
to force all subagents/teams to a cheap tier regardless of frontmatter.

**b) Tier effort per agent.** Subagent/skill frontmatter takes an `effort` field that
overrides the session level while that agent runs. Push fan-out/mechanical agents to
`low`/`medium`.

**c) Isolate verbose ops in a subagent regardless of model.** Running tests, fetching
docs, processing big logs — delegate them so the verbose output stays in the
**subagent's** context and only a short summary returns to the main conversation.
The main thread's cache is untouched by a subagent call (it just appends the
summary). This keeps the expensive main-conversation prefix small.

**d) Keep teams small and shut them down.** Each teammate burns until it exits. Agent
teams in plan mode use ~**7×** the tokens of a standard session. Keep spawn prompts
focused (teammates auto-load CLAUDE.md + MCP + skills on top of your prompt).

---

## 5. Context-window discipline (smaller context = fewer tokens every turn)

Token cost scales with context size — you re-send the whole context every turn, so a
bloated context taxes *every* subsequent message.

- **`/compact` at task boundaries (~natural breaks), not mid-task.** Compaction
  replaces history with a summary. Run it when you finish a phase, not when you
  notice degradation. Add focus: `/compact Focus on code samples and API usage`, or
  put a `# Compact instructions` block in CLAUDE.md. (The summarization call shares
  your cached prefix, so it's cheaper than it looks; the cost is mostly generating
  the summary.) Some practitioners compact around the ~60% context mark — but the
  docs' rule is **task boundary**, so prefer "finished a phase" over a fixed %.
- **`/clear` between unrelated tasks.** Stale context wastes tokens on every later
  message. `/rename` before clearing so you can `/resume` later if needed.
- **`/rewind` instead of `/compact` to abandon a wrong path** — it truncates back to
  an already-cached prefix (cheaper than building a new summary).
- **`/context`** shows exactly what's eating the window (system prompt, tools, memory,
  skills, history). **`/usage`** shows the per-session breakdown attributed to
  skills / subagents / MCP servers. Configure the status line to show context % live.
- **Read only the ranges you need.** Don't re-read a file already in context (the
  harness appends a `<system-reminder>` when a file changes and re-reads only if
  needed). Avoid pasting large blobs — reference files by path. Scope tool calls
  (specific grep/glob, targeted reads) instead of broad scans.
- **Write specific prompts.** "add input validation to the login fn in auth.ts"
  reads a couple files; "improve this codebase" triggers broad expensive scanning.
- **Use plan mode (Shift+Tab) for complex tasks** so a wrong direction is caught
  before you pay to implement it. Escape to course-correct early; test incrementally.

### Cut fixed per-session overhead
- **CLAUDE.md under ~200 lines** — it's in context for the whole session. Move
  workflow-specific instructions into **skills** (load on demand) instead.
- **Disable unused MCP servers** (`/mcp`); prefer CLI tools (`gh`, `aws`, `gcloud`)
  which add no per-tool listing. (MCP tool defs are deferred by default, but loaded
  ones still cost — and a server connect/disconnect can invalidate the cache.)
- **Offload preprocessing to hooks/skills** — e.g. a PreToolUse hook that greps a log
  for `ERROR` and returns only matches turns tens-of-thousands of tokens into hundreds.
- **Code-intelligence plugins** for typed languages → precise "go to definition"
  instead of grep-then-read-several-files.

---

## 6. Prompt caching — keep cache hits high, it's nearly free input

Claude Code caches automatically. **Cache reads bill at ~10% of the standard input
rate**, and on a subscription cache reads are effectively free against your plan. The
fixed overhead (system prompt, tool defs, CLAUDE.md) is a stable prefix that caching
absorbs across every turn. On a **Claude subscription Claude Code uses the 1-hour
cache TTL automatically** — your cache stays warm through breaks at no extra cost.
(It drops to 5 min only once you're over the limit and on paid usage credits.)

**Keep the cache warm — avoid mid-session actions that bust the prefix:**
- Switching **model** or **effort** mid-session → full uncached turn (each has its
  own cache). → pick both at the top. (`opusplan`'s toggle is the deliberate
  exception.)
- Turning on **fast mode** deep in a session, connecting/disconnecting an **MCP
  server**, enabling/disabling a **plugin that adds MCP**, adding a whole-tool **deny
  rule**, **`/compact`**, **upgrading Claude Code** mid-flow.
- Cache-**safe** (append-only, no bust): editing repo files, invoking skills/commands,
  `/recap`, `/rewind`, permission-mode changes, spawning subagents.
- **Resuming a long session after a Claude Code upgrade reprocesses the whole history
  uncached** — can be your single most expensive turn. (Another reason the guard's
  resume-by-reading-repo-state, with a *fresh short* session, is cheaper than a giant
  `--resume`.)
- Watch `cache_read_input_tokens` vs `cache_creation_input_tokens` (status line /
  transcript). High read-to-creation = caching is working; persistently high creation
  = something keeps changing your prefix.

---

## 7. Stretch / batch tactics

- **Batch related questions into one turn** — fewer re-orientation passes over the
  history; each turn re-sends the whole context.
- **Bound headless runs** (`--max-turns`, ≤N items/run) — see SKILL.md Flow 2.
- **Non-interactive credit pool (since 2026-06-15):** `claude -p` / Agent SDK / GitHub
  Actions draw from a **separate monthly credit pool**, not the interactive 5h/weekly
  caps. So a headless watcher won't eat your interactive session budget — but it can
  exhaust *credits*; the guard treats both as "the limit".
- **`/usage-credits`** sets a monthly spend cap on overflow usage credits if you want
  a hard ceiling.
- **1M context is included for Opus on Max** but a bigger window means bigger,
  pricier turns — don't fill it just because it's there; keep context tight anyway.

---

## 8. Know your POOLS — session, weekly, model-tier (and budget FLEETS against them)

Limits are not one number. Model them separately or a fleet will blindside you
(learned 2026-07-01: a 6-agent wave died mid-flight on the session limit and the
harness retried each dead agent — "agents kept respawning" until the reset):

- **5h session pool** — rolling window across the interactive session AND every
  subagent it spawns. **Fleet arithmetic:** N parallel agents burn ~N× your solo
  rate; a wave you'd survive solo can hit the wall in minutes. Before launching a
  fleet, ask: *can this wave FINISH before the reset boundary?* If the reset is
  <1h away and the wave is big, wait for the reset instead.
- **Weekly pool(s)** — all-models + a Sonnet-only sub-pool on Max. Tier fleets
  down (Sonnet/Haiku lanes) to spend the cheap pool first.
- **Model/tier pools** — top-tier models (Fable/Opus) may draw dedicated caps;
  routine lanes on cheaper tiers preserve top-tier headroom for judgment-heavy
  lanes.
- **Headless/credits pool** — `claude -p` watchers draw monthly credits, not the
  interactive caps (see §7) — but exhausted credits fail the same way; guard both.

**When a fleet dies on a limit:** do NOT relaunch into the wall (each retry burns
preflight/startup tokens and reads as respawn-thrash). Checkpoint durable state,
suppress automatic resumes until the reset (limit-aware backoff in watchdogs +
preflight-abort paths), then resume the orchestrator WITH result caching (e.g.
Workflow resumeFromRunId) so completed lanes return cached instead of re-running.

---

## TL;DR checklist (paste into a session-start habit)

- [ ] Interactive dev on Max → **`/model opusplan`** (Opus plans, Sonnet executes).
- [ ] Routine/mechanical session → **`/model sonnet` + `/effort medium`** (or Haiku+low).
- [ ] **Set model + effort ONCE at the top** — mid-session switches bust the cache.
- [ ] Subagents/fan-out → **`model: haiku|sonnet` + low/medium effort** in frontmatter
      (or `CLAUDE_CODE_SUBAGENT_MODEL`); isolate verbose ops in subagents.
- [ ] **`/compact` at task boundaries; `/clear` between unrelated tasks; `/rewind` to abandon a path.**
- [ ] CLAUDE.md < 200 lines; disable unused MCP; prefer CLI tools; read only needed ranges.
- [ ] Don't re-read files already in context; write specific prompts; batch questions.
- [ ] Keep prompt cache warm (high read / low creation); let the 1h subscription TTL work.
