---
name: local-coding-agent
description: >-
  Run a small LOCAL coding agent (opencode + Ollama, a 4B-class model on ~8 GB)
  and make it genuinely competent instead of "useless". Covers model choice on
  constrained hardware, the config that stops a small model denying its own
  tools, teaching correct tool use via exact recipes + a global AGENTS.md,
  removing trap/duplicate tools, cross-session memory a weak model can actually
  use (auto-inject recall + deterministic /remember write), a server-API
  verification harness, and reboot-durable service control. Use when setting up
  or debugging a local/offline coding agent, when a small local model refuses or
  misuses tools (file/web/GitHub "no access", invented CLI flags, wrong URLs),
  when giving a local agent persistent memory, or when deciding how to make a
  weak model reliable rather than routing around it.
---

# local-coding-agent — make a small local coding model actually useful

Distilled from running **opencode + Ollama** with a **Qwen3-4B** model on an **8 GB M1 Air**.
The throughline: a weak model's "it can't do X" is almost always **tool MISUSE, not missing
access**. Fix it by making the agent *smarter* (correct recipes, fewer/clearer tools, injected
context) — **never by pre-doing the work and telling the model to skip the tool.** Smarter, not
dumber. Everything below was verified on-device via the server API, not assumed.

## 1. Model choice on constrained hardware (~8 GB)
- **Agentic default = a small INSTRUCT (non-thinking) model.** Thinking models spiral in a big
  agent prompt on tight RAM (thousands of reasoning tokens, no tool call). A 4B instruct goes
  straight to tool calls. Rebuild it with enough context for tool schemas (≥16K).
- **Vision is a SEPARATE model, never the agentic default** — a thinking-VL model spirals worst.
- Two models max on 8 GB (one text-agent, one vision). Check free RAM before loading; a model that
  spills to CPU crawls.

## 2. Config that stops a small model sabotaging itself
In `opencode.json`:
- **`default_agent`: a LEAN agent**, not the stock heavyweight. A huge system prompt makes a 4B
  *deny its own tools* ("I lack file/web/GitHub access") even with tools attached and a small
  context. Define a `mini` agent: short prompt + only the core tools.
- **`disabled_providers`: hide the hosted free-model catalog** so the picker shows only your local
  models — otherwise users think a dozen models are "installed" when none are.
- **Prune tools to a non-overlapping set.** Duplicate/temptation tools wreck a small model: it
  grabbed a web-search MCP's `fetchGithubReadme` (and guessed the URL wrong) instead of `gh`.
  Disable redundant MCP tools so the ONE correct path is the only path. Fewer tools = better.

## 3. Teach correct tool use with EXACT recipes (prompt + global AGENTS.md)
A 4B invents CLI flags/fields (`gh --sort`, `full_name`, `html_url`) and guesses raw URLs. Give it
copy-paste-correct commands so it needn't invent:
- Put recipes in the agent prompt AND an **`AGENTS.md`** (opencode auto-loads it; it's the
  CLAUDE.md equivalent). **Put AGENTS.md GLOBALLY** (`~/.config/opencode/AGENTS.md`) — auto-discovery
  traverses *up* from the session dir, so a per-project file misses sessions opened elsewhere
  (Downloads, Desktop). Keep it concise (<150 lines; models follow ~150 instructions), hand-written,
  real command snippets over prose.
- Frame guidance as **task-recipes, not meta-instructions.** "To checkout a repo: `ls ~/Projects` →
  read → `gh repo clone` if missing" works; "manage your memory when appropriate" does not.
- Encode the gotchas the model actually hits: **a repo is a DIRECTORY** — globbing its name returns
  nothing (glob matches files), so the model concludes "doesn't exist" and quits; tell it to use
  `ls`/`bash`, not glob. Pin the OS shell dialect (macOS/BSD: `sed -i ''`, `stat -f%z`,
  `du -sh|sort -hr`) — Linux flags fail silently.
- "Auth doesn't work" is usually the wrong surface: `gh` GraphQL subcommands + git may work
  perfectly while raw REST (`gh api user`) throws transient 503s. Tell it to use `gh repo list/view
  --json`, never `gh api <rest>`. Add "if a command errors, fix syntax and retry — don't give up."
- **Guardrails must state the POSITIVE case, or a small model overgeneralizes them into refusals.**
  A one-sided rule — "do NOT commit/push unless the user explicitly asks" — made the 4B refuse to
  commit/build/open PRs *even when explicitly asked*, inventing a "user must confirm" policy that
  existed nowhere (push/PR plumbing was fully working the whole time). Every "do NOT X unless Y"
  needs its other half spelled out: **"when Y, DO X immediately — the user's request IS the
  approval; never ask for extra confirmation."** Pair it with the exact flow so the steps can't be
  fumbled: branch → edit → verify → commit → push → `gh pr create`. (Verified live: after the
  rewrite, one natural request produced a real draft PR end-to-end with zero refusals.)
See `RECIPES.md` for a ready-to-adapt AGENTS.md.

## 4. Cross-session memory a weak model can actually use
Do NOT bolt on a knowledge-graph memory MCP (≈9 tools) — it re-overwhelms the small model you just
un-overwhelmed. Split the two halves by reliability:
- **RECALL = automatic injection.** Point `opencode.json` `instructions` at a memory file
  (`"instructions": ["~/.config/opencode/agent-memory.md"]`). It's in *every* session's context, so
  the model answers from it with **zero tool calls** — recall can't fail because the model isn't
  asked to do anything. (Verified: a fresh session recalled a codeword it never read.)
- **WRITE = deterministic command, not model tool-calling.** A 4B *narrates* the append command as
  text instead of calling `bash`, so instruction-driven writes silently no-op. Make a `/remember`
  custom command whose body is a **bang-shell**:
  `` !`printf -- '- %s\n' "$ARGUMENTS" >> ~/.config/opencode/agent-memory.md` `` — the append runs
  during command expansion (shell), independent of the model. Invoke by typing `/remember <fact>` or
  `POST /session/{id}/command {command:"remember",arguments:"<fact>"}`. Users can also just edit the
  file. **Lesson: for weak models make recall automatic and writes deterministic — never rely on the
  model to self-manage memory via tools.**

## 5. Verify against the SERVER API, not the CLI
Drive `POST /session` + `POST /session/{id}/message` with the directory header and assert on the
returned **structured tool parts** — that's the surface the UI/phone uses. `opencode run` in
serve-attach mode ignores cwd for tool resolution (wrote a test file to `$HOME`) and its stdout tool
markers are unreliable to grep. Small models are stochastic: retry a live check a few times, and
give cold checks a longer timeout (the file index builds lazily after a restart — the cold case is
the post-reboot case). Have the harness clean up sessions/temp files it creates.

## 6. Keep the service alive & controllable
- Auto-start the model server + `opencode serve` from a login-scoped service (they're on-demand
  processes; a reboot otherwise leaves the whole thing dead and "broken").
- **Identify processes by PORT, never `pgrep/pkill -f <path>`** — the pattern matches any bystander
  shell whose command line contains the string (it SIGTERMed unrelated shells twice). Use
  `lsof -ti tcp:PORT` with an absolute path (a login-agent PATH may lack `/usr/sbin`).
- If a phone/hub controls it over a tailnet, pin Host/Origin to *your* tailnet suffix, not a bare
  `*.ts.net` (a stranger's Funnel page is also `*.ts.net`).

## The one principle
When a small model "can't", ask *what tool did it misuse and why*, then remove the confusion
(wrong recipe, too many tools, uninjected context) — don't route around the model. That's the line
between a local agent that's a toy and one that's useful.
