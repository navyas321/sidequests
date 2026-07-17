# RECIPES — drop-in config for a small local coding agent (opencode + Ollama)

Adapt paths/usernames. Verified with Qwen3-4B on an 8 GB M1 Air.

## opencode.json (the load-bearing keys)
```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "model": "ollama/qwen3-agent",
  "default_agent": "mini",                 // lean agent, NOT the heavy stock one
  "disabled_providers": ["opencode"],      // hide the hosted free-model catalog from the picker
  "instructions": ["/Users/you/.config/opencode/agent-memory.md"],  // auto-inject memory (recall)
  "mcp": {
    "websearch": { "type": "local", "command": ["npx","-y","open-websearch@2.1.11"],
      "enabled": true, "environment": { "MODE": "stdio", "DEFAULT_SEARCH_ENGINE": "duckduckgo" } },
    "context7": { "type": "local", "command": ["npx","-y","@upstash/context7-mcp"], "enabled": true }
  },
  "tools": {                               // kill trap/duplicate MCP tools a small model misuses
    "websearch_fetchGithubReadme": false,  // it grabbed this & guessed the URL instead of gh
    "websearch_fetchWebContent": false,
    "websearch_fetchCsdnArticle": false, "websearch_fetchJuejinArticle": false,
    "websearch_fetchLinuxDoArticle": false
  },
  "agent": {
    "mini": {
      "description": "Lean agent for small local models: short prompt, core tools only",
      "mode": "primary",
      "prompt": "You are a capable coding agent on the user's Mac (macOS/BSD: du -sh *, sort -hr; not GNU flags). You HAVE working tools — read/write/edit/glob/grep/list, bash, webfetch, websearch_search — USE them; never claim you lack file/web/GitHub access. GitHub: `gh` is authenticated and works; use gh SUBCOMMANDS (gh repo list/view --json ...), never `gh api <rest>` (REST 503s), never guess raw URLs. To read a repo: `ls ~/Projects` -> read local files -> `gh repo clone` if missing (a repo is a DIRECTORY; don't glob its name). If a command errors, fix the syntax and retry; don't give up.",
      "tools": { "write": true, "edit": true, "read": true, "bash": true, "glob": true,
                 "grep": true, "list": true, "webfetch": true,
                 "task": false, "todowrite": false, "todoread": false, "patch": false }
    }
  }
}
```

## ~/.config/opencode/AGENTS.md (GLOBAL — loaded for every session)
Keep it <150 lines, hand-written, command snippets over prose. Cover: read/checkout a repo
(`ls ~/Projects` → read → clone-if-missing, NOT glob), gh recipes (list/view/search/pr/issue +
the VALID `--json` fields, so it can't invent `--sort`/`full_name`/`html_url`), run/build by
project-type (`package.json`→npm, `pubspec.yaml`→flutter, `requirements.txt`→python, `Makefile`→make,
`*.ino`→arduino), and macOS/BSD gotchas (`sed -i ''`, `stat -f%z`, `du -sh|sort -hr`, `date -u`).
Also a "persistent memory" note: the memory file is auto-injected (don't read it); write with the
/remember command below.

**Git & PR section — write the guardrail TWO-SIDED** (a one-sided "do NOT commit unless asked"
makes a small model refuse even when asked):
```markdown
## Git & pull requests
Inspect freely: git -C ~/Projects/REPO status | log --oneline -10 | diff.
When the user asks you to change code, commit, push, or open a PR — their request IS the
approval. Do it immediately; NEVER refuse or ask for extra confirmation. You have push and
PR access (verified). Only rule: don't commit/push things the user did NOT ask for.
Full flow for "update the code, verify, open a PR":
git -C ~/Projects/REPO checkout -b feat/SHORT-NAME
# ...edit files, then verify (build/run/test per project type)...
git -C ~/Projects/REPO add -A && git -C ~/Projects/REPO commit -m "clear message"
git -C ~/Projects/REPO push -u origin feat/SHORT-NAME
gh pr create --repo OWNER/REPO --title "..." --body "what changed and why"
```

## ~/.config/opencode/command/remember.md (deterministic memory write)
```markdown
---
description: Save a durable fact/preference to persistent memory
---
!`printf -- '- %s\n' "$ARGUMENTS" >> ~/.config/opencode/agent-memory.md && echo "OK saved: $ARGUMENTS"`

The fact above was appended to persistent memory. Reply in one short line confirming what you saved.
```
The `` !`...` `` bang runs the shell during command expansion — the append happens even though the
4B would otherwise narrate the command instead of calling `bash`. Trigger: `/remember <fact>` in the
UI, or `POST /session/{id}/command {"command":"remember","arguments":"<fact>"}`.

## ~/.config/opencode/agent-memory.md (seed)
```markdown
# Agent memory (persistent across sessions). Auto-loaded via opencode.json "instructions".
# Durable facts/preferences only. Write via /remember or edit directly. One fact per line.
- The user is <handle>; repos are cloned under ~/Projects.
- This machine is 8 GB — keep builds/models light.
```

## Smoke assertion via the server API (not `opencode run`)
```python
# create a session bound to a dir, send one message, poll for completion, assert on tool parts
sid = POST("/session", {"title":"verify"})["id"]
POST(f"/session/{sid}/message", {"model":{"providerID":"ollama","modelID":"qwen3-agent"},
     "agent":"mini", "parts":[{"type":"text","text":"<task>"}]})
# poll GET /session/{sid}/message until an assistant message has time.completed,
# then assert the expected tool name appears in the tool parts. Retry 2-3x (stochastic). Delete the session.
```
