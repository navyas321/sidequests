# Resume-after-limit watcher (auto-continue a long loop across session-limit resets)

A long autonomous job (e.g. "drain the backlog, don't stop until done") will hit the 5h/weekly Claude
usage limit. The durable pattern: a **one-shot Scheduled Task armed at the limit's RESET time** that
fires a headless launcher which reads the repo's resume doc and continues — so the work picks itself
back up minutes after the limit resets, with zero human action.

## Mechanism (generic)
1. **Capture state durably BEFORE you run out** — keep a resume doc (`docs/STATUS.md`: goal, pending
   priorities, in-flight, how-to-resume) + `docs/journal/CHECKPOINT.json`, and the work queue in a
   committed file (`data/backlog.json`). The commit IS the checkpoint.
2. **Detect the reset time.** Claude's limit message / the claude.ai usage page shows "resets in Xh"
   / "resets HH:MM". `scripts/detect_limit.py` parses the CLI's limit output; the claude.ai page shows
   the 5h-block + weekly reset clocks.
3. **Arm a one-shot task at reset+buffer:**
   ```
   schtasks //Create //TN "<proj>-resume" //SC ONCE //ST <HH:MM after reset> \
     //TR "wscript.exe \"<repo>\scripts\run-<watcher>-hidden.vbs\"" //F
   ```
   The launcher (hidden vbs → hidden powershell → `claude -p --permission-mode bypassPermissions`,
   `ANTHROPIC_API_KEY` stripped for subscription auth) runs a prompt that says: *read docs/STATUS.md +
   CHECKPOINT.json and CONTINUE the loop — drain the backlog, commit per item, don't stop.*
4. **Re-arm each reset.** ONCE tasks self-consume (Next Run → N/A); re-register one for the next reset
   whenever you near the limit again. A periodic (e.g. 6h) backup watcher catches anything missed.
5. **Single-flight lock** (`%TEMP%\<proj>.lock`, pid+ts, stale>90m reclaimed, deleted on clean exit)
   so a manual run and the scheduled run don't race; surface "running" in any dashboard FROM THE LOCK
   (the detached launcher makes the Scheduled Task's lastResult read 0 even mid-run).

## Reference impl (life-in-tabs)
- One-shot: `life-in-tabs-resume` armed at the 5h-block reset → fires `scripts/run-backlog-watcher-hidden.vbs`.
- Backup: `life-in-tabs-backlog-watcher` every PT6H.
- Prompt: `scripts/backlog-watcher-prompt.txt` (STEP 0 reads STATUS.md first).
- Don't-stop rule: process open items until the backlog is 0 + verified; on limit, finish the current
  commit, re-arm the resume task, exit.
