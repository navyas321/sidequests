# REFERENCE.md — Claude Code memory, arbitration & compaction architecture

Companion to `SKILL.md`. This is the deep version — the "why" behind the runbook.
It captures the full architecture: how Claude Code arbitrates skills vs. memory vs.
tools vs. hooks, the complete context-management + compaction design, and the
memory/context slash-command reference. Loaded on demand (progressive disclosure).

Version-gated numbers (thresholds, buffer sizes, command renames) move fast and
several were pieced together from people reverse-engineering the bundle rather than
official docs — treat exact numbers as current-as-of-now, not contractual. The
architectural *shapes* are stable.

---

## 1. How Claude Code arbitrates skills, memory, and tools

There is **no single router** deciding "skill vs. memory vs. tool." Each mechanism
is gated differently and lives at a different point in the context lifecycle, so
they don't actually compete in one decision.

- **Memory (`CLAUDE.md`) is resident, not retrieved.** It isn't "looked up" when
  relevant — it is loaded into context at **session start** and stays the whole
  session. Claude Code walks up the directory tree from cwd to the repo root
  collecting every `CLAUDE.md`, plus user-level `~/.claude/CLAUDE.md` and
  managed-policy files, and **merges them additively**. Claude treats these as
  *context, not enforced configuration* — the system even wraps the file with a
  caveat that the context may or may not be relevant. To block an action
  regardless of what Claude decides, use a **PreToolUse hook**, not memory. Memory
  shapes the prior over everything; it never "fires."

- **Auto-memory is the retrieval-ish part.** `MEMORY.md` is a short **index** where
  each line points to a detailed file. Claude reads the index (always loaded), then
  pulls specific topic files when they seem relevant. Index = always-on; topic
  files = progressive.

- **Skills are lazily-loaded context gated by description-matching.** At startup
  only the **name + description** from each skill's YAML frontmatter enter the
  system prompt (a few dozen tokens each). The Skill tool uses a **dynamic prompt
  generator** that builds its description at runtime by aggregating the names +
  descriptions of all available skills — the model sees a *menu* of capabilities
  without their bodies. When a task matches a description, Claude uses bash to read
  `SKILL.md` from the filesystem, bringing its instructions into context; if those
  reference other files, Claude reads those too; when they mention executable
  scripts, Claude runs them via bash and receives only the **output** — the script
  code never enters context. So "deciding to use a skill" is just the model
  matching task-intent against a description string — the same intent-recognition
  it uses to pick any tool. It is **probabilistic**, which is why descriptions
  matter so much and why skills sometimes don't fire when you expect. **Hooks are
  deterministic, skills are probabilistic**: for rules that must hold 100% of the
  time use hooks; for rules where Claude's judgment is acceptable use skills.

- **Tools are standard function-calling.** Built-in tools (Read, Bash, Edit, Grep,
  WebFetch) and MCP tools are selected the normal way — the model reads tool
  descriptions resident in context and emits a tool call. MCP tool **names** load
  at startup like skill descriptions; the heavier **per-tool schemas are
  increasingly deferred-loaded** to save context.

- **Hooks aren't a model decision at all.** They run scripts automatically at
  specific lifecycle points; unlike advisory `CLAUDE.md`, hooks are **deterministic
  and guarantee the action happens**. A **PreToolUse hook returning exit code 2
  blocks the action before it executes** — the only hard guarantee in the system.
  They run **outside the context window** entirely.

**Mental model:** memory = always-on advisory prior; skills = description-matched
lazy context; tools = function-calls against resident descriptions; hooks =
deterministic event handlers the model can't override. The "arbitration" is really
just the model reading descriptions and matching intent, layered on top of whatever
memory is already resident.

---

## 2. Context management and compaction

The context window holds conversation history, file contents, `CLAUDE.md`, auto
memory, loaded skill bodies, MCP tool names, and system instructions — and
performance degrades as it fills ("context rot"), which is the constraint
everything else is designed around. There is a **three-layer compaction design**:

- **Microcompaction (continuous, cheapest).** When tool outputs get large, Claude
  Code saves them to disk and keeps only a **reference** in context. It's a cache
  policy: a **hot tail** of recent tool results stays fully visible; **cold
  storage** is everything else, referenced by path (auditable + re-readable by the
  agent). Applies to **Read, Bash, Grep, Glob, WebSearch, WebFetch, Edit, Write**.

- **Auto-compaction (near the wall).** Fires as you approach the limit — now around
  **83.5%** of the window (up from ~77–78%), with the reserved buffer reduced to
  roughly **33,000 tokens** (16.5% of 200K, down from 45,000). That buffer is space
  you can't use; it exists so there's room to generate the summary itself. **Older
  tool outputs are cleared first**, then the conversation is summarized if needed.
  The summary isn't freeform — it's a **structured "working state"**, reported as a
  roughly **nine-section contract** covering state, next steps, and learnings.

- **Manual `/compact [focus]` (task boundaries).** Trigger compaction at a natural
  boundary with optional focus, e.g. *"/compact focus on the API changes and ignore
  the test refactoring."* Heavy users recommend compacting **deliberately at ~60%**
  rather than waiting for the auto-trigger, because the summary is cleaner at a real
  stopping point.

- **The underlying primitive: the server-side Compaction API (`compact-2026-01-12`
  beta).** When input tokens exceed the trigger threshold, the API generates a
  summary, creates a **compaction block**, and on subsequent requests automatically
  **drops all message blocks prior to that block**, continuing from the summary.
  **`pause_after_compaction`** lets you pause after the summary is generated so you
  can inject additional content (e.g. preserving specific recent messages) before
  the response continues. Claude Code wraps this.

- **Rehydration preserves momentum.** After compacting, it re-injects the few things
  that keep you productive — **recent files, todos, and a continuation
  instruction**. Structural asymmetries to know:
  - **Project-root `CLAUDE.md` survives** — Claude re-reads it from disk and
    re-injects it.
  - **Nested `CLAUDE.md`** files are **not** re-injected automatically — they reload
    only the next time Claude reads a file in that subdirectory.
  - Most startup content reloads automatically after compaction; the **skill
    listing is the exception**.
  - So if an instruction vanished post-compaction, it was either conversation-only
    or in a nested file that hasn't reloaded.

- **compaction ≠ checkpoints.** Checkpointing snapshots **file state** before each
  edit, persists across sessions, and lets you restore code, conversation, or both.
  Compaction compresses the **conversation** to free context but **doesn't touch
  files on disk**. And there is **no real off-switch** — `autoCompactEnabled:false`
  in `settings.json` has no effect (the key isn't in the schema and is silently
  ignored). You **steer** compaction; you don't disable it.

- **Subagents get a separate context discipline.** They run in **isolated context**
  and return only a summary to the main thread, so research text never crowds the
  parent. For progress they use **delta summarization** — given a few new messages
  plus the running summary, produce a 1–2 sentence incremental update, building on
  the previous summary rather than reprocessing everything.

- **The lever that ties memory and compaction together:** durable facts
  (architecture, conventions, safety rules) belong in `CLAUDE.md` precisely because
  it's re-read and survives compaction intact — so the summarizer has less to
  preserve. A **`## Compact Instructions`** section in `CLAUDE.md` is a documented
  way to control what compaction keeps.

---

## 3. Slash commands worth keeping

**Structural note:** custom slash commands have been **merged into skills**
(shipped in v2.1.101). Files in `.claude/commands/` still work, but skills
(`.claude/skills/`) are now recommended. Both create `/command-name` shortcuts; if
a skill and command share a name, **the skill takes precedence**. The difference: a
skill can be invoked by `/name` **and** auto-invoked when its description matches.
You can't override built-ins. There are **60+ built-in commands** — type `/` to
filter.

High-value built-ins, grouped by the problem they solve:

- **Context/session:** `/context` (visualize exactly what's eating tokens — your
  first diagnostic), `/compact [focus]` (summarize now, with optional steering),
  `/clear` (fresh window between unrelated tasks — the most underused command),
  `/rewind` (undo edits / restore prior context; as of v2.1.191 it can even restore
  context from before a `/clear`), `/resume` and `/branch` (resume a thread;
  `/branch` was renamed from `/fork` and lets you fork at a clean point so the
  original never has to compact).
- **Memory:** `/init` (scaffold project `CLAUDE.md`), `/memory` (open memory files
  in your editor; also how you browse the auto-memory folder).
- **Planning/review:** `/plan` (toggles plan-permission mode — Claude proposes each
  action and waits; use before large refactors), `/diff`, and the bundled
  `/code-review [effort]` skill (more reliable than freeform "review my changes").
- **Focus:** `/goal` (keeps Claude driving toward a defined outcome across many
  turns), `/btw` (ask a side question mid-task without polluting the main context).
- **Cost/perf:** `/model`, `/effort` (match reasoning depth to the task instead of
  paying top-tier for boilerplate), `/cost`, `/usage`.
- **Extension/diagnostics:** `/hooks`, `/agents`, `/mcp`, `/plugin`, `/doctor`
  (installation health — press `f` to auto-fix), `/config`.

**Custom commands/skills — the frontmatter is the leverage.** Commands support YAML
frontmatter for `allowed-tools`, `argument-hint`, `description`, `model`, and
`context: fork`, with `$ARGUMENTS` capturing everything or `$1`/`$2` capturing
positional args. Patterns that pay off:

- A `/recap` or PR-summary command: `allowed-tools: Bash(git:*), Bash(gh:*)` over a
  body that runs `git diff` and writes a PR description in your style. Set
  `allowed-tools` or it prompts you on every `gh` call.
- **Namespace by concern** — `/test/add-edge-cases`, `/db/migration-draft`,
  `/refactor/rename-pattern` — scans far better than a flat list.
- **Pin the model** in critical commands (`model: claude-opus-4-8`) so a default
  change doesn't silently alter behavior.
- `context: fork` runs the command in an isolated context so it doesn't pollute your
  main thread — good for research-style commands.

**Don't speculatively build commands.** The advice that holds up: take the single
most-typed paragraph from your last week, drop it in a file, run it once, and keep
it if it worked.
