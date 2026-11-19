---
name: handheld-ftp-backup
description: >-
  Manage an Android gaming handheld's files from a PC over Wi-Fi FTP: inventory the storage, back up
  exactly what matters with a SHA-256 manifest, move saves between emulators and devices without
  ever overwriting one unbacked, reformat an SD card safely, and restore with read-back verification.
  Knows the Android traps: scoped storage blocks other apps from Android/data, a reformat changes the
  card's volume ID, and an app update can quietly move where saves are read from. Use when the user
  says "connect to my handheld's FTP", "copy my save from one device/emulator to the other", "back up
  the SD card", "format the card so files over 4 GB work", "my save is gone / the game started new",
  or "what's on the card, what should I keep". Ships ftpdu.py / ftpbackup.py / ftprestore.py (+ tests).
allowed-tools: Bash, PowerShell, Read, Write, Grep, Glob, WebFetch
argument-hint: "<device ip> <port> [inventory|backup|restore|save-transfer|reformat]"
---

# handheld-ftp-backup

A handheld's SD card holds two kinds of thing: replaceable bulk (ROMs, ISOs, game dumps) and
irreplaceable small files (saves, console-unique NAND backups, configs). Every rule here protects the
second kind. Saves are tiny, so there is never a reason not to back one up first.

## 0. Connect

- Run an FTP server app on the device and note host, port and **which root it serves** (internal
  storage or the SD card; many apps serve one at a time and must be switched in the app).
- The scripts log in anonymously; for a server with an account set `FTP_USER` and `FTP_PASS`. Plain
  FTP is unencrypted and exposes the storage to the whole LAN: use a trusted network and stop the
  server app when done. The server must support MLSD (most Android FTP apps do).
- Git Bash on Windows rewrites arguments that start with `/` into Windows paths:
  `export MSYS_NO_PATHCONV=1` before passing remote paths.
- Ask before copying anything **to** the device. The device usually has its games already; send only
  what was asked for (a mod, a save, a config), never a "helpful" copy of bulk data.

## 1. Inventory, then decide what to keep

```bash
python ${CLAUDE_SKILL_DIR}/scripts/ftpdu.py 192.168.1.50 2221 / inventory.tsv        # per-folder totals + full TSV
```

Show the user the per-folder totals and propose keep / drop with reasons. Typical keeps: saves (find
every emulator's save folder), console-unique dumps (NAND backups and their key files: keep these on
the PC, not only on the card), configs, and anything not re-obtainable. Typical drops: macOS junk
(`._*`, `.DS_Store`, `.Trashes`), console-encrypted content that only runs on the original console,
homebrew for a console the card no longer serves. The user decides.

## 2. Back up with a manifest

```bash
python ${CLAUDE_SKILL_DIR}/scripts/ftpbackup.py 192.168.1.50 2221 inventory.tsv D:/backups/handheld-2026-11-18 /Switch/ /roms/
```

Use a **new dated folder** for every backup (the script refuses a non-empty one unless `--resume`
continues an interrupted run, and even then re-downloads every file up to 16 MB, so an older save is
never kept by mistake). Retries dropped connections, gives up fast on permanent errors, checks every
size, writes `MANIFEST.sha256`. For a NAND image, also compare against the dumper's own hash file.

Restore with `ftprestore.py HOST PORT BACKUP_DIR [--skip PREFIX ...]`: it never overwrites a file that
differs on the device (a newer save is reported as a CONFLICT); `--force` first saves the device's
copy under `BACKUP_DIR/_device-copies-<time>/`, then replaces it.

## 3. Moving a save between devices or emulators

1. Find where the **destination app actually reads saves**: its own log or config prints the folder
   (do not infer it from another emulator's layout). File name rules differ: some key on the ROM file
   name, some on a game ID.
2. Check the format: size and type must match what the destination expects (a raw 512 KB DS save,
   a footer-carrying variant, a per-slot state). Convert only with a known tool.
3. **Back up the destination's existing save first,** with a date in the name, off the device.
4. Fully close the app (not just home-screen it), copy, then verify by read-back hash **and** by
   loading the game.
5. Write the reversal: "close the app, copy `<backup>` over `<path>`".

## 4. Reformatting an SD card (FAT32 4 GB limit)

1. Full backup with manifest (step 2) and confirm the manifest is complete.
2. Format **on the device** as **portable storage**. Not "internal": that encrypts the card to that
   one device. Android picks exFAT for large cards only when the device supports it, so step 5 checks.
3. The card gets a **new volume ID**. Re-pick it as the FTP root, and re-pick the ROM/save folders in
   every emulator that stored the old path, or they will point at a path that no longer exists.
4. Restore and verify (`ftprestore.py`: every size checked, small files re-read and hashed).
5. Prove the reason for the format: copy a real file over 4 GB and confirm it lands whole.

## 5. "My save is gone" after an update or a re-pick

- First, **stop writing**: do not let the game save over the slot.
- Check whether the app now reads saves from a different folder. A real case: an update started
  pinning the saves folder whenever the ROM folder was re-picked; after a card reformat it pinned the
  app's own `Android/data/<package>/files`. On Android 11+ ordinary apps cannot write there, even with
  "all files access" (the FTP server could not). Routes that often still work, depending on the
  device: `adb` or USB file transfer from a PC, or a root/Shizuku file manager. The old save was
  intact on the card the whole time.
- Read the exact code change between the two app versions and cite file and line before calling it a
  bug; then write a short report and a prompt for an independent reviewer to check the claims
  against the code, and propose the upstream fix.

## Gotchas

- If every upload fails with 550/551, the FTP root points at a path that no longer exists (the old
  card): re-pick the root in the app and restart its server.
- Prove the over-4 GB fix by copying a real file larger than 4 GB; a quick probe that only asks the
  server to create a big file can pass or fail for reasons that have nothing to do with the card.
- Keep the PC-side backup folder until the user has played on the restored card.
- Log what you did in the device's config journal (see `machine-config-journal`).

## Origin

From a session moving a Pokémon save between two Android handhelds, reformatting an old FAT32 card
for large Switch dumps (52 GB inventoried, 9.5 GB kept and restored with every save hash-verified),
and the save that "reset" after a launcher update moved its saves folder into storage nothing else
could write to.
