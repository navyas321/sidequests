# RELIABILITY — hard-won invariants for the scrum pipeline

Shared reference for `/feature` and `/bugfix`. Read this at the **Test & verify**
and **Release** gates. These rules come from real production failures on this
machine (the life-in-tabs hub + its headless dev autopilot). Each one cost hours;
each is now a checkable guard.

## The post-change SMOKE TEST (run at the Release gate — and in the watcher's preflight)

A change is NOT done until an automated smoke test passes. For this machine the
canonical script is `life-in-tabs/scripts/smoke-test.py` — run it after every
wave / autopilot run. It asserts, and you should assert for any project:

1. **All scripts PARSE.** Every `.ps1` must `[ScriptBlock]::Create` cleanly;
   every `.py` must `py_compile`. A script that doesn't parse silently no-ops.
2. **All data files are VALID.** Every JSON (`backlog.json`, `data/workflow/*.json`,
   `events.json`, `coordination.json`) must `json.load` without error and with a
   UTF-8(-sig) decode — a BOM or a stray byte drops the file from the board.
3. **No duplicate IDs / stale hardcoded values** in the data or the UI.
4. **UI invariants** (for web UIs): no horizontal overflow at 375x812, hyperlink
   targets point where they should, no raw stale counts baked into HTML.
5. **Health is FRESH.** Any watcher/service health record reflects a run within
   its expected cadence (not "all STALE").

If the smoke test has no project-specific form yet, CREATE it — it is the single
highest-leverage artifact for an autonomous pipeline.

## Four rules that bit us (do not relearn these)

1. **ASCII-ONLY in scripts.** Windows PowerShell 5.1 reads `.ps1` as **cp1252**
   unless it has a UTF-8 BOM. A single non-ASCII char (em-dash `—`, smart quote,
   `→`, `•`, `✓`) becomes mojibake → the whole script fails to parse → it never
   runs. The autopilot once corrupted its OWN launcher this way and no-op'd for
   hours. Use `-`, `'`, `"`, `...`, `->` in all `.ps1/.vbs/.bat`. (Python files:
   always `encoding="utf-8"` on every read/write — Windows defaults to cp1252.)

2. **"Task runs but does nothing" → run the script DIRECTLY.** Task Scheduler's
   "Last Run Time" updating is NOT proof the script executed. If a scheduled job
   appears to fire but produces no work/log, run its entry script by hand
   (`powershell -File x.ps1 -DryRun`) and watch for a parse error. Don't trust
   the wrapper's exit code.

3. **Concurrent edits to the SAME file silently REVERT each other.** On this
   machine there are multiple writers: you, parallel subagent waves, AND the
   headless dev autopilot (a Scheduled Task that drains the backlog and commits).
   When two edit one file, the later commit clobbers the earlier. Therefore:
   - **Commit your hand-edits BEFORE launching any wave that touches those files.**
   - **One editor per file per wave** — give each parallel agent a disjoint file set.
   - **The autopilot is a concurrent actor.** Before a big interactive wave, check
     its lock (`%TEMP%\life-in-tabs-backlog-watcher.lock`); if it's draining, work
     on files it won't touch, or wait for the lock to clear. Claim items in
     `data/coordination.json` (`claimed[]`) and SKIP IDs other actors claimed.
   - **After a wave lands, grep-verify your key fixes survived**; re-apply if reverted.

4. **Verify LIVE, not stale.** A passing build/curl-200 does not prove the UI is
   correct. Cards/boards can show stale cached values (nextRun, last-done, "all
   STALE" health) while the underlying state is fine — and vice-versa. Render-test
   the real surface (375x812 dark via the preview MCP), and exercise the REAL
   client path (proxied Host over Tailscale), not just `127.0.0.1`.

## Retro discipline

Every `/feature` and `/bugfix` ends with a one-line retro naming **what guard
would catch this class of bug earlier**. If that guard is a check the smoke test
could run, ADD it to the smoke test. The pipeline should get harder to break
over time.
