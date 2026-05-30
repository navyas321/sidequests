---
name: photo-reconciler
description: >-
  Reconcile a Google Photos album export (a zip of media) against an existing
  Apple iCloud library so ONLY genuinely-missing photos/videos get uploaded —
  no duplicates. Use when migrating Google Photos to iCloud, de-duplicating
  between the two, or validating that an export is fully present in iCloud.
  Windows + "iCloud for Windows" only.
allowed-tools: Bash
argument-hint: "[path-to-google-export.zip]"
---

# Photo reconciler (Google Photos → iCloud, no duplicates)

Upload only the album items that aren't already in iCloud. The engine is
`${CLAUDE_SKILL_DIR}/scripts/reconcile.py` (subcommands below). This **uploads
to the user's iCloud account**, so it is gated: always dry-run and get explicit
confirmation before staging, and never auto-delete the user's files.

Install deps once: `pip install -r ${CLAUDE_SKILL_DIR}/requirements.txt`.
Pick a working dir on a drive with space (NOT the system drive); pass it as
`--work <dir>`. Defaults assume the iCloud folder is
`C:\Users\<you>\iCloudPhotos\Photos` — override with `--icloud`.

## The critical correctness gate
The iCloud library is mostly **HEIC**. Pillow can't read HEIC without
`pillow-heif`. If it's missing, every iCloud HEIC fails to hash, iCloud looks
*empty*, and the tool flags ALL Google photos as "new" → it re-uploads
everything and creates massive duplicates. The script registers pillow-heif and
prints an iCloud **error rate** — if that rate is high, STOP and fix deps; do
not trust the comparison.

## Workflow
1. **Verify + extract the export.** Confirm the zip is a complete, valid archive
   (`python -c "import zipfile;print(zipfile.ZipFile(r'<zip>').testzip())"` →
   `None`). Extract it to your working dir (NOT the system drive — these exports
   are large).

2. **Index iCloud** (slow part — downloads each on-demand file to hash it):
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/reconcile.py --work <dir> index-icloud --workers 8
   ```
   Concurrency overlaps download latency. It's resumable (re-run to continue).
   Add `--dehydrate` if the system drive is tight (frees each local copy after
   hashing; needs `--free-floor <GB>`). Watch the printed **error rate** ≈ 0.

3. **Index the Google export:**
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/reconcile.py --work <dir> index-google <extracted-folder>
   ```

4. **Compare → unique lists:**
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/reconcile.py --work <dir> compare
   ```
   Writes `unique_images.txt` / `unique_videos.txt`. **Sanity-check the count:**
   if "to upload" ≈ *all* Google items, the comparison failed (HEIC/empty-iCloud
   bug) — do NOT proceed.

5. **Dry-run, then a canary, then the rest** (gate on user confirmation):
   ```bash
   # dry-run (copies nothing):
   python ${CLAUDE_SKILL_DIR}/scripts/reconcile.py --work <dir> stage --dry-run \
     --list <dir>/unique_images.txt --list <dir>/unique_videos.txt
   # canary: stage ~25 first, confirm they appear at icloud.com, THEN the rest:
   python ${CLAUDE_SKILL_DIR}/scripts/reconcile.py --work <dir> stage --limit 25 \
     --list <dir>/unique_images.txt
   ```
   Staging copies files **directly into** the iCloud Photos folder (the modern
   iCloud-for-Windows v14+ client uploads them automatically — there is no
   "Uploads" subfolder). The collision-safe copier never overwrites an existing
   file (it appends `_1`, …), so it won't clobber real iCloud photos.

6. **Confirm the upload.** The filesystem **cannot** tell you an upload
   succeeded — with "Download originals" on, an uploaded file still looks like a
   normal local file. Ground truth is the **iCloud app's upload counter** or
   **icloud.com/photos**. Have the user confirm new items appear there.

7. **Verify accounting** (every album item accounted for; staged files intact):
   ```bash
   python ${CLAUDE_SKILL_DIR}/scripts/reconcile.py --work <dir> verify \
     --list <dir>/unique_images.txt --list <dir>/unique_videos.txt
   ```
   A few "NOT found" are normal — usually blank/near-duplicate junk frames that
   iCloud de-duplicated server-side, or files iCloud re-encoded on ingest.

## Safety
- Always dry-run and show counts before any real copy; canary before bulk.
- Never permanently delete the user's files — recommend, let them confirm.
- Don't touch iCloud account settings or sharing/permissions.
- Note the **EXIF caveat**: photos whose EXIF survived the Google export keep
  their original dates; those that lost it get dated "today" (import date) and
  sit at the top of the library. Not fixable after upload.
