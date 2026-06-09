---
name: steam-shortcut
description: >-
  Add a non-Steam game (any .exe / launcher) to the Steam library by safely
  editing shortcuts.vdf. Use when the user wants to "add a game to Steam", "add
  a non-Steam shortcut", bring an EA app / Epic / GOG / itch game into Steam, or
  make a desktop program show up in Steam (e.g. to stream it via Remote Play to
  a Steam Deck / Legion Go). Cross-platform; parses and preserves existing
  shortcuts.
allowed-tools: Bash, Read
argument-hint: "[--name <name> --exe <path>] | --list"
---

# Steam shortcut skill

Add a non-Steam game to the Steam library by editing the binary `shortcuts.vdf`
that Steam keeps per user. The bundled script
`${CLAUDE_SKILL_DIR}/scripts/add_shortcut.py` does the work and runs fine
standalone (pure standard library, no dependencies).

Why this is useful beyond "adding a game": once an `.exe` is a Steam shortcut it
becomes eligible for **Steam Remote Play** — so a game blocked on SteamOS/Linux
by anti-cheat (EA FC, etc.) can run on a Windows desktop and **stream** to a
Steam Deck / Legion Go.

## The one rule that matters

**Steam must be CLOSED before writing.** Steam holds `shortcuts.vdf` in memory
and rewrites it from memory on exit — editing it while Steam runs gets silently
overwritten on the next shutdown. The script refuses to write if it detects
Steam running (override with `--force` only when you know Steam is closed).

## Flow

1. **Inspect** — see where Steam is, which user account(s) exist, and what's
   already added (read-only, safe while Steam is running):

   ```bash
   python "${CLAUDE_SKILL_DIR}/scripts/add_shortcut.py" --list
   ```

   If more than one user account is listed, note the numeric id — you'll pass it
   as `--user <id>` below.

2. **Close Steam.** Cleanly, so it flushes and releases the file:
   - Windows: `& 'C:\Program Files (x86)\Steam\steam.exe' -shutdown` then wait
     for `steam.exe` to disappear.
   - Linux/macOS: quit Steam from its menu, or `steam -shutdown`.

3. **Add the shortcut.** The exe path must exist on *this* machine (a shortcut
   is a pointer, not a copy of the game):

   ```bash
   python "${CLAUDE_SKILL_DIR}/scripts/add_shortcut.py" \
     --name "EA SPORTS FC 26" \
     --exe  "C:\Program Files\Electronic Arts\EA SPORTS FC 26\FC26.exe"
   # optional: --start-dir <dir>  --launch-options "<args>"  --icon <file>
   #           --user <id>  --steam-root <dir>
   ```

4. **Reopen Steam.** The game appears in the library under the *Non-Steam*
   category. The change now persists across restarts: Steam read it on launch,
   so it rewrites it back on every future exit.

## Safety properties (how it avoids corrupting an existing list)

- **Backs up** `shortcuts.vdf` to `shortcuts.vdf.bak` before writing.
- **Round-trip self-check**: before writing, it parses the current file and
  re-serializes it; if the bytes don't match exactly, it refuses to write. This
  proves the serializer reproduces *your* file faithfully, so appending one
  entry can't mangle the others.
- **Append, not overwrite**: existing shortcuts are parsed and preserved; the
  new entry takes the next free index.
- **Duplicate guard**: re-running with the same name + exe is a no-op.
- **Readback verification** after writing.

## Notes

- Cross-platform: auto-detects Steam on Windows (registry + common paths),
  Linux (`~/.steam/steam`, `~/.local/share/Steam`, Flatpak), and macOS
  (`~/Library/Application Support/Steam`). Override with `--steam-root`.
- The `appid` is generated the standard way (`crc32(exe+name) | 0x80000000`),
  which is also the basis Steam uses to locate custom grid/library artwork.
- This only creates the shortcut. It does **not** install the game, set Proton
  compatibility, or work around anti-cheat.
