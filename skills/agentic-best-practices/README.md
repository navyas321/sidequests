# agentic-best-practices

> A working checklist of Anthropic's current (2025–2026) guidance for building
> with Claude — apply the relevant section to the task, skip what doesn't fit.

A Claude Code [skill](SKILL.md). It auto-loads whenever the work is LLM-shaped and
non-trivial: building an agent or multi-agent system, writing a complex/system
prompt, orchestrating subagents, designing a tool or MCP server, authoring a
Claude Code skill, or deciding whether a task needs an agent at all.

## What's inside

- **[SKILL.md](SKILL.md)** — the lean, standing checklist that stays in context.
  Two laws (*simplicity first*, *context is the scarcest resource*) followed by
  sections on prompting Claude 4.x, agent vs. workflow design, Claude Code
  skills/subagents/hooks/CLAUDE.md, context engineering, tool & MCP design, and
  reliability/evaluation.
- **[PRACTICES.md](PRACTICES.md)** — the deep version with rationale and source
  links; read it when you need the *why* or a citation. Loaded on demand
  (progressive disclosure) so it never costs tokens until needed.

## How to use it

**With Claude:** just start the work ("help me design this agent", "review this
tool schema", "is this better as a workflow or an agent?") and the skill fires on
its description. Or invoke it explicitly with `/agentic-best-practices`.

It's **read-only** (`allowed-tools: Read, Grep, Glob, WebFetch`) — pure guidance,
no scripts, no side effects, no Python dependencies. Any OS.

## The one-line summary

Find the simplest thing that works (a good single LLM call beats a workflow beats
an agent beats many agents), keep the context window full of high-signal tokens,
and close a verification loop the agent can run itself — so it self-corrects
instead of stopping at "looks done."
