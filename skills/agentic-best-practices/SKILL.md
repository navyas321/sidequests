---
name: agentic-best-practices
description: >-
  Current (2025-2026) Claude + agentic AI best practices distilled from official
  Anthropic engineering guidance — covering prompting Claude 4.x, agent vs.
  workflow design, Claude Code skills/subagents/hooks/CLAUDE.md, context
  engineering, tool & MCP design, and reliability/evaluation. Use when building
  an agent or multi-agent system, writing a complex or system prompt,
  orchestrating subagents, designing a tool or MCP server, authoring a Claude
  Code skill, deciding whether a task needs an agent at all, or whenever the
  LLM-shaped work is non-trivial and you want it to be context-efficient,
  verifiable, and reliable.
allowed-tools: Read, Grep, Glob, WebFetch
---

# Agentic best practices (Claude 4.x era)

A working checklist of Anthropic's current guidance for building with Claude.
Apply the relevant section to the task at hand; skip what does not apply. The
deep version with rationale and source links is in
[PRACTICES.md](PRACTICES.md) — read it when you need the "why" or a citation.

## The two laws that drive everything

1. **Simplicity first.** Find the simplest thing that works. A single optimized
   LLM call with retrieval and good examples beats a workflow; a workflow beats
   an agent; one agent beats many. Only add complexity (steps, tools, agents)
   when an *eval* shows a measurable gain. Agents cost ~4x the tokens of chat;
   multi-agent ~15x — reserve them for high-value, parallelizable work.
2. **Context is the scarcest resource.** Performance degrades as the window
   fills ("context rot"). Almost every other practice is a corollary: keep the
   window full of high-signal tokens, and close a verification loop so the agent
   self-corrects instead of stopping at "looks done."

## Prompting Claude 4.x

- Start from a **minimal prompt on your strongest model**; add instructions and
  examples only to fix *observed* failure modes, not hypothetical ones.
- Structure the system prompt with **XML tags or Markdown headers**: background,
  instructions, tool guidance, output format. Write at the right "altitude" —
  specific enough to guide, general enough to give strong heuristics. Avoid both
  brittle hardcoded logic and vague hand-waving.
- Be **specific**: name the file, the scenario, what "done" looks like, and an
  existing pattern to follow. Vague prompts get vague work.
- **Curate a few diverse canonical few-shot examples** rather than enumerating
  every edge case.
- Use `IMPORTANT` / `YOU MUST` emphasis *sparingly*. If Claude keeps ignoring a
  rule, the prompt is probably too long and the rule is getting lost — prune.
- Provide rich context via file references, pasted images/screenshots, URLs, or
  piped data; let Claude pull its own context with tools rather than
  front-loading everything.

## Agent design & orchestration

- **Workflow vs. agent:** a *workflow* is LLM calls on predefined code paths
  (predictable, cheap, controllable); an *agent* dynamically directs its own
  process in a loop (flexible, costly, harder to control). Choose a workflow
  when the path is knowable; an agent only when you genuinely cannot hardcode
  the path.
- Build on the **augmented-LLM block**: an LLM with retrieval + tools + memory
  behind a clean, well-documented interface.
- **Five workflow patterns** cover most needs before you reach for an agent:
  - *Prompt chaining* — fixed sequential subtasks with programmatic gate checks.
  - *Routing* — classify input, dispatch to a specialized handler.
  - *Parallelization* — sectioning (independent subtasks concurrently) or voting
    (same task N times for confidence/coverage).
  - *Orchestrator-workers* — a lead LLM decomposes dynamically, delegates, then
    synthesizes (subtasks NOT predefined).
  - *Evaluator-optimizer* — generator + critic loop against a clear rubric.
- **Agent execution loop:** gather context → take action → **verify** → repeat.
  Always verify before continuing so errors do not compound.
- **Multi-agent is a poor fit** for shared context, tight sequential
  dependencies, or real-time coordination — including most coding. Use it for
  broad research, work exceeding one context window, or many complex tools.
- For each **subagent**, give an explicit objective, output format, tool/source
  guidance, and clear boundaries to prevent duplication and drift. Embed
  effort-scaling rules (1 agent for fact-finding; several for comparisons; 10+
  with defined roles for deep research). Run independent tools/subagents
  concurrently.
- Prefer **upgrading the model** over merely doubling the token budget. Start on
  raw LLM APIs; if you use the Claude Agent SDK, understand what it does under
  the hood. Sandbox before granting real autonomy.

## Claude Code: skills, subagents, hooks, CLAUDE.md

- **Slash commands are now Skills.** `.claude/commands/x.md` and
  `.claude/skills/x/SKILL.md` both create `/x`; Skills are preferred (supporting
  files, invocation control, subagent execution, dynamic context).
- **CLAUDE.md:** run `/init`, then keep it short and human-readable. For each
  line ask "would removing this cause a mistake?" — if not, cut it. Include only
  broadly-applicable, non-guessable facts (custom bash commands, non-default
  style, test runners, repo etiquette, env quirks). Exclude anything inferable
  from code, standard conventions, or that changes often. Check it into git; use
  gitignored `CLAUDE.local.md` for personal notes.
- **Create a Skill** when you keep pasting the same checklist, or when a
  CLAUDE.md section grew from a fact into a procedure.
  - Every skill is a directory with `SKILL.md` + YAML frontmatter. The
    `description` is what Claude uses to auto-load — state *what it does AND when
    to use it*, key use case first, with natural trigger keywords
    (description + when-to-use ≤ ~1,536 chars).
  - **Progressive disclosure:** keep `SKILL.md` lean (< 500 lines); move large
    references/specs/examples into separate files and link them so they load on
    demand. The body stays in context across turns, so write standing
    instructions ("do this", not "why") — Claude does not re-read the file.
  - Bundle scripts in `scripts/`, reference via `${CLAUDE_SKILL_DIR}` so paths
    resolve at any install scope. Scripts are *executed*, not read into context.
  - `disable-model-invocation: true` for manual side-effecting commands
    (`/commit`, `/deploy`); `user-invocable: false` for background knowledge.
    `allowed-tools` pre-approves safe tools. Inject live data with `` !`cmd` ``.
- **Subagents** (`.claude/agents/`): one focused responsibility, a clear
  "when to delegate" description, and the *minimum* tool set (e.g. Read/Grep/Glob
  for a read-only reviewer). Use them to preserve main-context, enforce tool
  constraints, and route cheap work to faster models via the `model` field.
- **Hooks** for things that must happen *every time* — they are deterministic
  while CLAUDE.md is only advisory. Configure in `settings.json` on the right
  lifecycle event (PreToolUse/PostToolUse/Stop…). Treat them as a security
  boundary: they run arbitrary shell with your credentials, so review before
  enabling, and use PreToolUse hooks to block dangerous operations.
- **MCP:** connect a server when you keep copying data from another tool. Check
  a `.mcp.json` into the repo for shared tools; choose scope deliberately. Vet
  servers before trusting them. Prefer **CLI tools (`gh`, `aws`, `gcloud`)** over
  MCP where possible — they are the most context-efficient.
- **Manage context aggressively:** `/clear` between unrelated tasks,
  `/compact <instructions>` for focused summaries. After two failed corrections
  on the same issue, `/clear` and rewrite the prompt rather than piling on.

## Context engineering

- Curate the **smallest set of high-signal tokens** for the model's finite
  attention budget. More context is not better.
- Prefer **just-in-time retrieval**: store lightweight identifiers (paths,
  queries, URLs, IDs) and load data at runtime, letting the agent discover
  context through exploration (progressive disclosure).
- **Diagnose before fixing.** Match the technique to the bottleneck:
  - Dialogue/reasoning rot → **compaction** (`compact_20260112`): summarize the
    window and reinitiate with a high-fidelity summary. Default for long chats.
  - Re-fetchable tool-output bloat → **tool-result clearing**
    (`clear_tool_uses_20250919`): lightest, cheapest, server-side, lossless.
    Tune `keep` (3-4 if rarely re-referenced, 6-8 if cross-referenced); set the
    clear trigger well below the compaction trigger; `exclude_tools: ["memory"]`.
  - Cross-session persistence → the **memory tool** (`memory_20250818`):
    file-based store outside the window; view `/memories` first, then persist
    debugging insights, architectural decisions, intermediate results. Harden
    the backend (path-traversal defense, size caps, file-backed).
  - Combine all three for large workloads.
- Have the agent take **structured notes** (NOTES.md, to-do list) persisted
  outside the window. Delegate focused work to **clean-context subagents** that
  return only a condensed 1-2K-token summary.
- Latest models (Opus 4.6-4.8, Sonnet 4.6) have a 1M-token window; Sonnet
  4.5/4.6 and Haiku 4.5 are **context-aware** (track their own remaining budget).
  Use the token-counting API to estimate before sending and handle
  `model_context_window_exceeded` gracefully (save state, split into subagents).

## Tool use & MCP design

- The **tool description is by far the most important factor.** Write 3-4+
  sentences: what it does, when (and when NOT) to use it, what each parameter
  means, caveats/limits, and what it does *not* return. Onboard it like a new
  hire — make implicit context explicit.
- Build **a few thoughtful, consolidated tools** matched to agent affordances,
  not a wrapper per API endpoint. Group related actions under one tool with an
  `action` param. Namespace by service (`github_list_prs`). Use specific names
  (`search_customer_orders`) and unambiguous params (`user_id`, not `user`).
- Add `input_examples` (1-5 schema-valid examples) for complex/nested/
  format-sensitive inputs, and `strict: true` to guarantee schema conformance.
- **High-signal responses:** return only fields Claude needs; use semantic,
  stable identifiers over opaque UUIDs/MIME types; offer a concise/detailed
  format toggle; paginate/filter/truncate with steering hints when large.
- `tool_choice`: `auto` (default), `any`, `tool`, `none`; steer propensity via
  the system prompt rather than always hard-forcing. Note `any`/`tool` and
  forced tool use are **not supported with extended thinking**.
- **Parallel calls** happen by default for independent read-only ops. Return
  exactly one `tool_result` per `tool_use` (matched by id), all in the next user
  message, **before any text**. For skipped calls, still return a result with
  `is_error: true`.
- Handle failures with `is_error: true` plus an **instructive** message ("Rate
  limit exceeded. Retry after 60s."), not "failed".
- Treat `tool_result` content as **untrusted** (indirect prompt injection) — keep
  external/web/email content inside tool_result blocks, never in system text.
- **At scale:** Tool Search Tool (`defer_loading: true`, keep 3-5 hot tools,
  ~85% token cut) for big tool sets; programmatic/code-execution tool calling
  (~37% cut) to filter large intermediate results before they hit the model.
- Iterate tools against realistic evals (accuracy, runtime, call count, tokens,
  errors); have Claude analyze transcripts to refine descriptions.

## Reliability & evaluation

Reliability is a **closed verification loop**, not a model property. The dominant
failure is "looks done": with no executable check, the agent stops when output
is plausible and the human becomes the verification loop.

- **Give the agent a check it can run** every task — tests, build exit code,
  linter, fixture diff, screenshot-vs-design. **Make it gate the stop** (a
  `/goal` condition re-checked each turn, or a Stop hook that blocks until the
  check passes).
- **Require evidence, not assertion:** paste the test output, the exact command
  and its result, or a screenshot. If you cannot verify it, do not ship it.
- **Verify end-to-end as a real user** (browser automation / clicking through),
  not via unit tests or a dev-server ping alone.
- **Fix root causes**, never suppress/swallow/work around an error to make a
  check go green.
- **Adversarial review before "done":** a fresh-context subagent sees only the
  diff + criteria (not the authoring reasoning) and tries to refute the result.
  Scope it to **correctness and stated requirements only** — a reviewer told to
  find gaps always finds some, and chasing all of them causes over-engineering.
- **Eval-driven development:** write 20-50 realistic tasks from actual failures,
  each with unambiguous pass/fail (two experts would agree) and a reference
  solution proving it is solvable, *before* building. Grade **outcomes, not
  paths**. Make evals uncheatable (no shortcut/hardcoded answer = reward
  hacking). Use partial credit; pick pass@k vs pass^k to match the product.
  **Read transcripts** — it is the core skill. Isolate every trial (fresh
  state). Calibrate LLM-judges against human experts.
- **Guardrails:** screen inputs/outputs with a *separate* model instance;
  graduated permissions (allow / approve / block); sandboxing; layer
  injection defenses at model, harness, tool, and environment levels.
- **Human checkpoints:** plan mode as an approval gate; train for calibrated
  uncertainty (pause and ask on ambiguity rather than assume).
- **Durable state for long runs:** commit per change with descriptive messages;
  keep an immutable feature/test list as JSON (removing tests is unacceptable);
  read git history + progress log at session start; **one feature per session**;
  smoke-test prior work before new work.
