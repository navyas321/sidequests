# PRACTICES.md — Agentic best practices, with rationale and sources

Companion reference to `SKILL.md`. This file is loaded on demand; it carries the
"why" behind each rule and the source links. Everything here is grounded in
Anthropic's official 2025-2026 engineering guidance for the Claude 4.x era
(Opus 4.x / Sonnet 4.x, Claude Agent SDK, Claude Code).

## The two governing principles

**Simplicity.** Anthropic's "Building effective agents" post is blunt: find the
simplest solution and only add complexity when evals prove a measurable gain.
The cheapest-to-most-expensive ladder is: single optimized LLM call (with
retrieval + examples) → workflow → single agent → multi-agent. Cost is a real
constraint — agents use roughly **4x** the tokens of a chat interaction and
multi-agent systems roughly **15x**, so they only pay off on high-value,
heavily-parallelizable tasks. Prefer upgrading the model over doubling the token
budget.

**Context as scarcest resource.** "Effective context engineering" reframes
prompt engineering as *context engineering*: curating the smallest set of
high-signal tokens for a finite attention budget. Recall and accuracy degrade as
the window fills ("context rot"). Nearly every Claude Code best practice reduces
to managing context and closing a verification loop.

## Prompting Claude 4.x

- Begin minimal on your best model; add instructions/examples only to address
  *observed* failure modes. Over-specified prompts bury the important rules.
- Organize with XML tags or Markdown headers (background, instructions, tool
  guidance, output format). Design at the right "altitude": specific enough to
  guide behavior, flexible enough to be strong heuristics; avoid brittle
  hardcoded logic and avoid vague guidance.
- Be specific in task prompts: name the file, the scenario, testing
  preferences, the likely bug location, what "fixed" looks like, and an existing
  pattern to follow.
- Curate a small set of diverse canonical few-shot examples rather than
  enumerating edge cases.
- Use `IMPORTANT`/`YOU MUST` sparingly; persistent rule-violations usually mean
  the file is too long and the rule is getting lost — prune it.

Sources: effective-context-engineering-for-ai-agents; best-practices.

## Agent design & orchestration

Anthropic draws a sharp line between **workflows** (LLMs + tools on predefined
code paths — predictable, lower cost/latency) and **agents** (LLMs dynamically
directing their own process in a loop — flexible but costlier and harder to
control). The universal building block is the **augmented LLM** (retrieval +
tools + memory behind a clean, documented interface).

Five composable workflow patterns, in increasing flexibility:

1. **Prompt chaining** — fixed sequential subtasks with programmatic gate checks
   between steps to catch errors early.
2. **Routing** — classify input, dispatch to a specialized prompt/handler.
3. **Parallelization** — *sectioning* (independent subtasks concurrently) and
   *voting* (same task N times for confidence/coverage).
4. **Orchestrator-workers** — a lead LLM decomposes the task dynamically (subtasks
   NOT predefined), delegates to workers, synthesizes results.
5. **Evaluator-optimizer** — a generator and a critic loop until a clear rubric
   is met. Only use when you have clear criteria and iteration demonstrably
   helps.

Reserve **fully autonomous agents** for open-ended problems where you cannot
hardcode the path and can trust extended decision-making with guardrails and
sandboxing. Recommended execution model: **gather context → take action →
verify work**, looped. Verification strength order: rule-based/linting first,
then visual (screenshots/renders), then LLM-as-judge for fuzzy criteria.

**Multi-agent** (from the multi-agent research system post) is for high-value,
heavily parallelizable work, information exceeding one context window, or
interfacing with many complex tools. It is a *poor* fit for shared context, tight
sequential dependencies, or real-time coordination — including most coding. Give
each subagent an explicit objective, output format, tool/source guidance, and
boundaries. Embed effort-scaling rules (1 agent / a few calls for simple
fact-finding; several for comparisons; 10+ with defined roles for complex
research). Direct search broad-to-narrow. Let agents help refine their own tools
and prompts (a tool-testing agent cut task time ~40%). Evaluate early on ~20
representative cases with a single LLM-as-judge plus human review. Build for
reliability under non-determinism: checkpoint/resume, production tracing, and
external-memory state before hitting context limits.

Start on raw LLM APIs (many patterns are a few lines of code). If you adopt the
Claude Agent SDK, understand what it does under the hood.

Sources: building-effective-agents; multi-agent-research-system;
building-agents-with-the-claude-agent-sdk.

## Claude Code: skills, subagents, hooks, CLAUDE.md, MCP

**Doc-level change:** custom slash commands have been merged into Skills. A file
at `.claude/commands/deploy.md` and a skill at `.claude/skills/deploy/SKILL.md`
both create `/deploy`; Skills are now recommended because they add supporting
files, invocation control, subagent execution, and dynamic context injection.

Core workflow: **Explore → Plan (plan mode) → Implement → Commit.** Skip plan
mode only for one-sentence-diff changes (typos, log lines, renames); use it for
multi-file changes, unclear approaches, or unfamiliar code.

**CLAUDE.md:** bootstrap with `/init`; keep short and human-readable. Include
broadly-applicable, non-guessable facts (custom bash commands, non-default code
style, test runners, repo etiquette, env quirks, gotchas). Exclude anything
inferable from code, standard conventions, frequently-changing info, or long
tutorials. Move sometimes-relevant domain knowledge and multi-step procedures
OUT into Skills (load on demand). Check into git; use gitignored
`CLAUDE.local.md` for personal notes; `@path` to import/compose; place at
home/project/parent/child scope.

**Skills:** create one when you keep pasting the same instructions/checklist, or
when a CLAUDE.md section grows from a fact into a procedure. Each skill is a
directory with `SKILL.md` + YAML frontmatter; only `description` is truly
required — it is how Claude decides when to auto-load. Write it to state *what it
does AND when to use it*, key use case first, with natural trigger keywords
(description + when-to-use capped ~1,536 chars). **Progressive disclosure:** keep
`SKILL.md` under 500 lines, move large refs/specs/examples to separate files and
reference them so they load only when needed. The body stays in context across
turns once invoked, so write standing instructions (what to do, not why); Claude
does not re-read the file. Bundle scripts in `scripts/`, reference via
`${CLAUDE_SKILL_DIR}` (scripts are executed, not loaded). Frontmatter controls:
`disable-model-invocation: true` for side-effecting manual commands;
`user-invocable: false` for background knowledge; `allowed-tools` to pre-approve
safe tools (review project skills before trusting a repo — they can grant broad
access). Inject live data with `` !`command` `` (or a fenced `! block) so the
prompt arrives with current state inlined. Run a skill in isolation with
`context: fork` plus an agent type when it has explicit task instructions; do not
fork pure-guideline skills (the subagent gets no actionable prompt).

**Subagents** (`.claude/agents/` or `~/.claude/agents/`): for side tasks that
would flood main context with logs/search/file contents you will not reference
again. Give each a single focused responsibility, a clear "when to delegate"
description, and the minimum tool set (Read/Grep/Glob for a read-only reviewer).
Use them to preserve context, enforce tool constraints, specialize behavior, and
route cheap work to faster models (e.g. Haiku) via the `model` field. Delegate
research and verification explicitly. Tell a reviewer subagent to flag only gaps
affecting correctness or stated requirements, not style.

**Hooks:** for actions that must happen every time with zero exceptions — hooks
are deterministic, CLAUDE.md is advisory. Configure in `settings.json` with the
right lifecycle event (PreToolUse, PostToolUse, Stop, etc.) and matchers; ask
Claude to write them and browse with `/hooks`. Treat hooks as a **security
boundary** — they run arbitrary shell with your credentials; review before
enabling and use PreToolUse hooks to block dangerous operations.

**MCP:** connect a server (`claude mcp add`) when you keep copying data from
another tool. Check `.mcp.json` into the repo for shared project tools; pick
local/project/user scope deliberately. Vet servers and review their tool
descriptions — they consume context and run with your access. Define an MCP
server inline in a subagent's frontmatter to keep its tools out of main context.
Prefer CLI tools (`gh`, `aws`, `gcloud`, `sentry-cli`) over MCP where possible —
most context-efficient; install `gh` so Claude avoids unauthenticated rate
limits.

**Context hygiene:** `/clear` between unrelated tasks; `/compact <instructions>`
for focused summarization; `/btw` for throwaway questions. Course-correct early
(Esc to redirect, Esc+Esc or `/rewind` to restore state); after two failed
corrections on the same issue, `/clear` and rewrite the prompt. Scale
horizontally with parallel sessions (git worktrees, web, agent teams) and
Writer/Reviewer patterns on fresh contexts. Use non-interactive mode
(`claude -p` with `--output-format json`/`stream-json`) for CI/pipelines; scope
permissions tightly with `--allowedTools` in headless runs. For larger features,
have Claude interview you (AskUserQuestion) and write a self-contained SPEC.md,
then execute it in a fresh session.

Named failure patterns to avoid: kitchen-sink session (→ `/clear`); repeated
corrections (→ `/clear` + better prompt); over-specified CLAUDE.md (→ prune or
convert rules to hooks); trust-then-verify gap (→ always provide verification);
infinite unscoped exploration (→ scope it or use a subagent).

Sources: best-practices; skills; sub-agents; hooks-guide; mcp;
equipping-agents-for-the-real-world-with-agent-skills.

## Context engineering

- Treat context as finite with diminishing returns; expect context rot. Curate,
  do not just rely on a big window.
- **Just-in-time retrieval:** store lightweight identifiers (file paths, stored
  queries, URLs, IDs) and load data at runtime via tools. Enable progressive
  disclosure. A hybrid strategy (pull a little up front for speed, fetch more on
  demand) often works best.
- **Diagnose the bottleneck before fixing:** compaction for dialogue/reasoning
  rot; tool-result clearing for re-fetchable tool bloat; the memory tool for
  cross-session persistence; combine for large workloads.
- **Compaction** (`compact_20260112`): default for conversations approaching the
  limit. Write compaction instructions that maximize recall first (architectural
  decisions, unresolved bugs, key facts, open questions, progress/state), then
  iterate to drop redundant tool output. High-level facts survive; obscure
  specifics are lost.
- **Tool-result clearing** (`clear_tool_uses_20250919`): lightest, cheapest,
  server-side, no-inference, lossless (results re-fetchable). ~84% token
  reduction over 100 turns, ~29% perf gain. Tune `keep` (3-4 if rarely
  re-referenced, 6-8 if cross-referenced). Set the clear trigger well below the
  compaction trigger (e.g. clear at 100K, compact at 180K; on 200K models clear
  at 50K, compact at 120K). `exclude_tools: ["memory"]` so saved knowledge is
  never evicted.
- **Memory tool** (`memory_20250818`): file-based store outside context that
  survives sessions (+39% combined with context editing). Agent views
  `/memories` first, then persists debugging insights, architectural decisions,
  intermediate results. Harden: path-traversal defense, file and total size
  caps, file-backed storage.
- Have the agent keep structured notes (NOTES.md, to-do list) outside the window
  and pull them back later. Delegate to clean-context subagents that each return
  only a condensed 1-2K-token summary.
- Models: Opus 4.6-4.8, Sonnet 4.6, Fable/Mythos 5 have a 1M-token window;
  Sonnet 4.5/4.6 and Haiku 4.5 add context awareness (track remaining budget).
- Extended-thinking token mechanics: thinking tokens count against the window
  when generated but are auto-stripped from later turns; you must return the
  unmodified thinking block alongside its `tool_result` during a tool-use cycle.
  Use the token-counting API to estimate before sending; handle
  `model_context_window_exceeded` gracefully (pause, save state to memory, or
  split into subagents). Prefer first-party context-management APIs over custom
  orchestration; monitor `context_management.applied_edits` telemetry to tune
  triggers.

For long-running multi-session harnesses: use a dedicated **setup agent** in the
first context window (distinct prompt) to scaffold the environment; create a
comprehensive **feature-list JSON** (all features marked incomplete; agents may
only flip the pass/complete field, never edit/delete the list); provide an
`init.sh` and a progress log; **git from turn one** with descriptive commits;
per-session orientation (verify cwd, review git history + progress + feature
list before any work); **one feature per session**; mandatory health checks /
E2E tests through the real dev server before and after.

Sources: effective-context-engineering-for-ai-agents;
effective-harnesses-for-long-running-agents; context-management blog;
tool-use-context-engineering cookbook; context-windows docs.

## Tool use & MCP design

- **Description is the highest-leverage lever** — "by far the most important
  factor in tool performance." 3-4+ sentences: what it does, when (and when not)
  to use it, each parameter's meaning, caveats/limits, what it does NOT return.
  Onboard the tool like a new hire; make implicit context explicit (query
  formats, terminology, resource relationships).
- Give every parameter a clear description; mark `required`; use enums for
  constrained values.
- Build a few thoughtful, high-impact tools, each with a distinct purpose;
  consolidate related operations under one tool with an `action` param. Match
  tools to agent affordances, not human workflows (`search_contacts` over
  `list_contacts`). Namespace by service; use specific tool names and
  unambiguous parameter names (`user_id`, not `user`).
- `input_examples` (1-5 schema-valid: minimal, partial, full) for complex/nested/
  format-sensitive inputs, only where the schema does not make usage obvious.
  `strict: true` to guarantee schema conformance.
- **Responses:** only high-signal fields; semantic, stable identifiers over
  opaque UUIDs/MIME types; a concise vs detailed format enum; pagination, range
  selection, filtering, truncation with steering instructions. Experiment with
  XML/JSON/Markdown structure per task.
- **`tool_choice`:** `auto` (default), `any`, `tool`, `none`. Steer propensity
  via the system prompt rather than always hard-forcing. `any`/`tool` and forced
  tool use are NOT supported with extended thinking.
- **Parallel/sequential:** independent read-only ops run in parallel by default
  for latency; side-effecting/ordered ops run sequentially. Return exactly one
  `tool_result` per `tool_use`, all together in the next user message, matched by
  `tool_use_id`, with all `tool_result` blocks BEFORE any text. Skipped call →
  return `is_error: true` with a brief explanation.
- **Errors:** put them in `content` with `is_error: true`; write instructive
  messages stating what went wrong and what to try next.
- **Security:** treat `tool_result` content as untrusted — keep external/web/
  email/API content inside tool_result blocks (never system or plain user text)
  to mitigate indirect prompt injection. Use MCP tool annotations to disclose
  open-world access or destructive changes.
- **At scale:** Tool Search Tool (`defer_loading: true`, keep 3-5 hot tools,
  discover the rest on demand; ~85% token reduction) when tool defs exceed ~10K
  tokens or 10+ tools. Programmatic/code-execution tool calling for 3+ dependent
  calls or large intermediate datasets (~37% reduction, fewer inference passes);
  with MCP, present tools as a code/filesystem API, process large results in the
  execution environment, return only summaries (keeps intermediate data and PII
  out of model context).
- **Address your biggest bottleneck first:** context bloat from tool defs → Tool
  Search; large intermediate results → programmatic calling; parameter errors →
  `input_examples`. Use the latest Opus for complex/ambiguous tool scenarios
  (handles many tools, asks for missing params; lighter models may infer them).
- Iterate against realistic evals (accuracy, runtime, tool-call count, tokens,
  errors); have Claude analyze transcripts and chain-of-thought to refine tool
  descriptions.

Sources: writing-tools-for-agents; advanced-tool-use; code-execution-with-mcp;
tool-use docs (define-tools, handle-tool-calls, parallel-tool-use).

## Reliability & evaluation

Reliability is a closed verification loop, not a model property. The dominant
failure is "looks done": absent an executable check, the agent stops at
plausible output and the human becomes the verification loop, so silent mistakes
(hallucinated success, untested E2E features, silent truncation, reward-hacked
passes) wait to be noticed.

- **Give a runnable check every task** (tests, build exit code, linter, fixture
  diff, screenshot-vs-design) and **make it gate the stop** — a `/goal`
  condition re-checked each turn by a separate evaluator, or a Stop hook that
  runs the check and blocks the turn until it passes.
- **Require evidence, never assertion** (paste output / the command and its
  result / a screenshot). If you cannot verify it, do not ship it.
- **Verify E2E as a real user** (browser automation), not unit tests or a
  dev-server ping alone — agents routinely pass unit tests yet fail E2E.
- **Fix root causes**; never suppress/swallow/work around an error to go green.
- **Adversarial review before "done":** fresh-context subagent sees only the diff
  + criteria and tries to refute the result, so the author is not the grader.
  Scope it to correctness and stated requirements only — a reviewer told to find
  gaps always finds some, and chasing them all causes over-engineering and
  defensive code for impossible cases.
- **Eval-driven development:** 20-50 realistic tasks from actual user failures,
  each with unambiguous pass/fail (two experts agree) and a reference solution
  proving it solvable, written before building. Read transcripts religiously —
  the core skill. Grade outcomes, not paths (rigid path-checking penalizes valid
  creative solutions). Design tasks/graders so passing genuinely requires
  solving the problem (no shortcut/hardcoded answer = reward hacking). Guard
  against grading bugs (over-rigid matching like 96.12 vs 96.124991, ambiguous
  specs, unreproducible stochastic tasks); specify exact filepaths and formats.
  Use partial credit and decompose multi-step tasks. Pick pass@k (one working
  solution suffices) vs pass^k (consistency needed) to match the product.
  Isolate every trial (fresh state, no carry-over). Calibrate LLM-judges against
  human experts; combine automated evals, production monitoring, A/B tests, and
  transcript review.
- **Guardrails:** run guardrails as a separate model instance screening
  inputs/outputs. Graduated permissions (always-allow safe routine /
  require-approval consequential / block high-risk); allowlists and OS-level
  sandboxing. Layer prompt-injection defenses at all four levels: model, harness,
  tool, environment.
- **Human checkpoints:** plan mode as an approval gate; calibrated uncertainty
  (pause, raise concerns, seek clarification, or decline on ambiguity) balanced
  against needless interruption.
- **Durable state for long runs:** commit per change with descriptive messages;
  keep a structured progress log alongside git history and read both at session
  start; make feature lists and tests immutable (removing/editing tests hides
  missing functionality); one feature per session; smoke-test prior work before
  starting new. Manage context as a reliability resource (`/clear` between tasks;
  after two failed corrections, clear and restart with a better prompt).
- Use subagents for investigation and verification so heavy file-reading happens
  in a separate context.

Sources: demystifying-evals-for-ai-agents;
effective-harnesses-for-long-running-agents; best-practices; trustworthy-agents;
building-effective-agents.

## Key source URLs

- https://www.anthropic.com/engineering/building-effective-agents
- https://www.anthropic.com/engineering/multi-agent-research-system
- https://claude.com/blog/building-agents-with-the-claude-agent-sdk
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://www.anthropic.com/engineering/advanced-tool-use
- https://www.anthropic.com/engineering/code-execution-with-mcp
- https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- https://www.anthropic.com/research/trustworthy-agents
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
- https://code.claude.com/docs/en/best-practices
- https://code.claude.com/docs/en/skills
- https://code.claude.com/docs/en/sub-agents
- https://code.claude.com/docs/en/hooks-guide
- https://code.claude.com/docs/en/mcp
- https://claude.com/blog/context-management
- https://platform.claude.com/docs/en/docs/build-with-claude/context-windows
- https://platform.claude.com/docs/en/docs/build-with-claude/tool-use
- https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools
