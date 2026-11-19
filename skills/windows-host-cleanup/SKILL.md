---
name: windows-host-cleanup
description: >-
  Reclaim disk space, audit everything that autostarts, and deal with stuck or orphaned processes on a
  Windows 10/11 PC without deleting anything the owner still needs. Measures where space really
  went, proposes a ranked list before deleting, prefers reversible actions, shows the whole
  autostart list (every common source, with Sysinternals Autoruns for the rest) with ranked removal
  advice, and diagnoses a process that will not die instead of
  rebooting it away. Use when the user says "C: is almost full", "clean up the C drive", "what's safe
  to delete", "remove temp and dev files", "what starts with Windows", "why does this pop up at
  sign-in", "disable these startup items", "this process won't die / access denied", or "do some dev
  cleanup". Ships a read-only autostart_inventory.ps1.
allowed-tools: Bash, PowerShell, Read, Write, Grep, Glob
argument-hint: "[space|autostart|process|dev] [drive or process name]"
---

# windows-host-cleanup

Two rules carry this skill: **list before you delete**, and **reversible beats permanent**. The owner
decides what goes. The agent's job is an accurate, complete, ranked list and a clean way back.

## 1. Disk space

1. **Measure first.** Biggest folders under the user profile, `%TEMP%`, `%LOCALAPPDATA%`,
   `ProgramData`, and top-level drive folders. Note what is **in use** (modified today, or held open by
   a running process): an active game install cache in `%TEMP%` looks like junk and is not.
2. **Propose a table** with size, what it is, why it is safe or not, and the action (delete / Recycle
   Bin / move / leave). Typical safe candidates: temp files older than a day, `CrashDumps`, old
   installer downloads for software that is installed, regenerable caches (npm `_npx`, pip, pyright),
   stray CI or build artifact folders, stray copies of shader caches, the agent's own scratch files.
3. **Never in a "cleanup" without an explicit yes:** games, saves, user documents, photos, and agent
   session/transcript stores. Some agents keep their long-term memory inside the transcript folder,
   so an age-based prune there can delete it; exclude memory directories by name before any prune.
4. **The Recycle Bin is not free space.** Space returns only when it is emptied. On removable and
   external drives, treat deletes as permanent and say so: Windows does not recycle deletes on
   removable media, and some external drives keep recycled files the bin never lists.
5. Same size is not proof of a duplicate, and "this folder's main file has a copy" does not make the
   whole folder a duplicate. Hash or compare file lists before removing "duplicates".
6. **Moving instead of deleting** (game data or caches to another drive): copy, compare counts and
   bytes, repoint the app, confirm from its log, then remove the source. Never a one-step move.
7. Report before and after free space, and what was skipped because it was in use.

## 2. Autostart audit

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/autostart_inventory.ps1"              # table with on/off state
powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/autostart_inventory.ps1" -Csv a.csv   # for a ranked write-up
```

- Show the **whole** list. Task Manager's Startup tab misses services, scheduled tasks, RunOnce and
  Active Setup; a "top 5" answer to "what starts with Windows" will be called out. The script covers
  the common sources (its header lists what it does not cover: drivers, shell extensions and other
  deep hooks); for an exhaustive audit, also run Sysinternals Autoruns.
- Rank removal recommendations with a one-line reason each (hardware no longer fitted, feature not
  used, duplicate of another app). Give a KEEP list with the purpose of each item (streaming host,
  VPN, audio, peripherals, anything a running service depends on).
- **Disable the way the OS does,** so the owner can undo it in the normal UI: Task Manager's
  Startup tab (the `StartupApproved` flag) for Run-key and Startup-folder items, Settings > Apps >
  Startup for Store app tasks (state 2 to 1), and `Disable-ScheduledTask` for tasks. Uninstall only
  on request.
- Startup **scripts** (`.vbs`, `.cmd`) that launch several programs stop at the first error: a line
  pointing at an uninstalled exe silently stops everything after it. Check each referenced path exists.
- Verify after the next sign-in that what should start did start (ports answering, processes up).

## 3. A process that will not die

Before "just reboot", find out why:

- `taskkill` says "no running instance" while the process still shows: it has exited but a thread is
  stuck in a **kernel wait**, so no user-mode kill can reach it. Check `HasExited`, thread wait reasons,
  open handles and sockets (Sysinternals `handle`), and the parent.
- Open sockets on a stuck process point at the network driver's send path; GPU-heavy exits point at
  the display driver (a GPU driver restart is a cheap test). Note which test changed nothing.
- A kernel debugger or full dump is the deep option: ask first, and size the install, since the
  owner may care about disk space and leftover services.
- Write down how to reproduce it (start then quit the game) so a fix can be tested without a reboot.

## 4. Dev and agent leftovers

Look for long-running interpreters and test servers (`python -m http.server`, headless browsers with
`--remote-debugging-port`, `node` dev servers), stray git worktrees, and disabled-but-present scheduled
tasks. Kill only what you can prove is orphaned and yours; long-running services that belong to the
machine's purpose stay. Record the "found clean" list so the sweep is not repeated next week.

## 5. Record it

Every change gets a line in the machine's config journal (see `machine-config-journal`): what, why,
how to reverse. Cleanup that freed space gets before/after numbers.

## Origin

From a gaming PC's C: drive running down to single-digit GB during back-to-back game installs, a
startup audit where the first answer listed 5 items and the machine had about 20, a startup script silently aborted by a removed exe, and a
game process that exited into an unkillable kernel wait.
