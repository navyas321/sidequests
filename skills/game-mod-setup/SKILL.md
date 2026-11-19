---
name: game-mod-setup
description: >-
  Install a PC game plus a community mod list (from a guide, forum post or YouTube video description)
  so that every change is reversible, lands on the right drive, and is proven to load from the mod
  loader's own log rather than by eyeballing the game. Covers source trust, download handling,
  install placement and slow-drive traps, load-order and launcher gotchas, "does it actually work"
  checks, status/ETA reporting during long installs, and the final cleanup. Use when the user says
  "install this game and these mods", "set up the mods from this video", "install the latest squad
  update / patch / texture pack", "is the mod working", "make the mods easy to restore", "move the
  game to another drive", "clean up the archives", or "uninstall it and everything it left behind".
  Ships modledger.py (snapshot / diff / park / hash-verified restore) + tests.
allowed-tools: Bash, PowerShell, Read, Write, Edit, Grep, Glob, WebFetch, WebSearch
argument-hint: "<game> [mod list URL or video]"
---

# game-mod-setup

Modding sessions go wrong in the same few ways: files land on the wrong drive, a mod "installs" but
its loader silently skips it, a one-step move strands half a user folder, and nobody can say what the
mod changed when it is time to take it off. The fix is a ledger: snapshot before, diff after, park
instead of delete, and read the loader's log before saying "it works".

## 0. Before downloading anything

1. **Pin the target.** Exact game build and edition (Steam / Xbox app / EA / GOG), and the mod list's
   own required version. Xbox app games normally install to an open `XboxGames` folder that can be
   modded; some older installs still sit behind a locked `WindowsApps` folder, and some exes there
   refuse to be read even when the folder is writable.
   A squad/patch update has a **data cutoff date**: find it before installing ("transfers up to
   which date?") instead of discovering it in game.
2. **Where should it live?** Ask once, then honour it everywhere: game, mods, downloads, caches and
   archives. If the user says "everything on C", every later step (including the moves of finished
   downloads) follows it. If they change their mind, cancel queued moves rather than finishing them.
3. **Check the drive, not just free space.** Many-small-file data (mod packs, map caches, emulators'
   shader caches) crawls on exFAT drives with large clusters, which also have no hard links or
   journaling. On removable and external drives, treat deletes as permanent: Windows does not send
   deletes on removable media to the Recycle Bin, and on some external drives recycled files never
   show up in the bin to restore. Real-time antivirus scanning every extracted file is the other big slowdown; an
   exclusion for the install folder can help, but say so and get consent before adding one.
4. **Anti-cheat check.** Look for kernel anti-cheat (BattlEye `BEDaisy`, EAC, Ricochet-style drivers)
   before any DLL-proxy mod. Online modes plus injected DLLs can mean an unappealable ban. See the
   `game-render-injection` skill for the full check.
5. **Source trust.** Prefer the original author's page or repo and the links in the guide the user
   gave. Avoid re-upload mirrors and "one-click" installers that bundle leaked or patched binaries.
   Check release hashes when published. If the agent cannot download (site blocks automation,
   login, captcha), give the user **exact links in order** and take over again once files land.

## 1. Snapshot, then install

```bash
python ${CLAUDE_SKILL_DIR}/scripts/modledger.py snapshot "<game dir>" -o baseline-<game>.json
# ... install the mod(s) ...
python ${CLAUDE_SKILL_DIR}/scripts/modledger.py diff "<game dir>" baseline-<game>.json      # exactly what changed
```

- Keep a per-game note of the order you installed things in, and which files each mod added.
- **Mods that ship their own instructions** (an `.ini` block to paste, a camera/stadium value set)
  are part of the install: apply them, back up the file first, and record the edit.
- Some tools rewrite their own config on exit (ReShade writes `ReShade.ini` when the game closes).
  Edit those files **with the game closed**, or your edit is silently overwritten.
- Generic steps that repeat per item (stage a costume for every character, add a kit per team) are
  worth writing once as a reusable procedure for the user rather than repeating by hand.

## 2. Prove it loaded (from the loader, not the screen)

"Looks the same" cannot tell a correct no-op from a module that failed to start.

- Read the loader's log after the next launch: Sider prints `Module (x.lua) is NOT activated` when a
  Lua module throws in `init` (observed: its Lua sandbox offered no `pcall`/`require`); ReShade, OptiScaler, SKSE, BepInEx
  and most loaders log every add-on they load and every one they refuse.
- Launch the way the mod expects: many packs need their own `start`/launcher exe, and the bare game
  exe crashes or loads vanilla.
- When a setting "does nothing" (aspect-ratio fix, camera mod), reason about **why the setting
  exists** before concluding it is broken: test the vanilla exe, then the mod, and compare logs.
- Verify persistence: close the game, reopen, and check the settings and files survived.

## 3. Long installs: report progress with numbers

During multi-GB downloads/installs the user will ask "status? ETA?" every few minutes. Answer before
they ask: bytes done / total, current rate, ETA, and whether the rate is **moving** (sample twice
a minute apart). A flat rate on a slow drive is a stall to investigate (drive type, antivirus, a
dialog waiting for input), not something to keep reporting.

## 4. Moving a game or its user folder

Never a one-step `robocopy /MOVE`. Copy, compare counts and bytes, repoint the app (its ini,
launch option or shortcut), confirm from the app's own log that it uses the new path, then delete or
set aside the source. Warn the user not to launch the game mid-move: a partial move looks exactly
like a full data reset.

## 5. Turning mods off, and uninstalling

```bash
python ${CLAUDE_SKILL_DIR}/scripts/modledger.py park "<game dir>" --name <set> --to "<park dir>" --added-since baseline-<game>.json
python ${CLAUDE_SKILL_DIR}/scripts/modledger.py restore "<park dir>" <set>      # later, hash-checked
```

- **Park, don't delete,** when the user might want it back. Keep the park folder outside any folder a
  library scanner treats as "one subfolder per game".
- A store's "verify files" does not remove files a mod added. The baseline diff does.
- Full uninstall: uninstall the game, then remove what it leaves behind (user folder, mod folders,
  map/data caches, registry layers a mod registered machine-wide). Back up anything small and unique
  first (configs, saves, a reinstall note) and list the rest before deleting.

## 6. Cleanup at the end (ask first)

List installers, archives and staging folders with sizes, mark which are safe (the game is installed
and verified, the archive is re-downloadable), and delete only on a yes. "Is it safe to remove the
installer files?" deserves a per-item answer, not a blanket one.

## Gotchas

- An agent that cannot see the user's screen should ask for a screenshot of the setting, not guess
  its name. "I don't see that option" means the guess was wrong; go read the docs for that version.
- Different loaders can fight over the same proxy DLL name (`dxgi.dll`, `winmm.dll`, `d3d11.dll`):
  check the diff before installing a second one.
- Video tutorials age fast: check the mod list's date against the game build before following it.

## Origin

Distilled from a run of real sessions installing a football sim with a dozen community packs, a
JRPG costume-mod set, a driving sim with a map mod, a squad-update data pack and a PC port on an
exFAT drive. Each lesson above cost at least one confused restart: a silently skipped Lua module,
an ini rewritten on exit, a half-moved user folder that looked like lost progress, and installs that
crawled until the drive and antivirus were checked.
