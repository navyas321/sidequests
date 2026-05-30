# sidequests

> A grab-bag of witty helper tools — born as *side quests* while solving
> something else.

Each tool is packaged as a [Claude Code](https://code.claude.com) **skill**
(a runbook the agent follows, with bundled Python scripts), but every script
also runs perfectly well on its own from the command line. Use them with Claude,
or just `python` them directly.

## The tools

### 📷 `photo-reconciler` — Google Photos → iCloud, no duplicates
Reconciles a Google Photos album export (a zip of media) against your existing
Apple iCloud library and uploads **only the genuinely-missing** photos/videos —
no duplicates. Perceptual hashing (with the all-important **HEIC** fix),
internal de-duplication, threaded on-demand hashing, collision-safe staging into
the iCloud-for-Windows folder, and a verification pass. Knows the sharp edges:
HEIC decoding, cloud-file hydration/dehydration, the v14+ upload mechanism, disk
management, and the fact that the filesystem *can't* confirm an upload (only the
iCloud app / icloud.com can). *Windows + iCloud for Windows.*

### 🎵 `source-finder` — what's that song?
Give it a video or audio clip and it identifies the song/media and returns the
source (artist + title + link). It's a **fallback ladder**, because acoustic
fingerprinting (Shazam) only matches studio originals:

1. **Read the video frames** — on-screen text, branding, or a live chat guessing the song.
2. **Acoustic fingerprint** (Shazam) — for studio originals.
3. **Transcribe the lyrics** (Whisper, with EQ + vocal isolation) — works for *covers*, since it's the words, not the recording.
4. **Web-search the lyrics** and cross-reference everything — then **verify**.

> Built the day Shazam *failed* on a clip — which turned out to be a streamer's
> own original song. Fingerprinting couldn't know it; the lyrics could.

## Install (as a Claude Code plugin)

```text
/plugin marketplace add navyas321/sidequests
/plugin install sidequests@sidequests
```

Then just ask Claude *"what's the song in this clip?"* (with a file), or run
`/photo-reconciler path/to/export.zip`.

## Use standalone (no Claude)

```bash
# deps per tool
pip install -r skills/photo-reconciler/requirements.txt
pip install -r skills/source-finder/requirements.txt

# find a song
python skills/source-finder/scripts/frames.py clip.mov --crop right
python skills/source-finder/scripts/extract_audio.py clip.mov -o eq.wav --eq
python skills/source-finder/scripts/transcribe.py eq.wav --model large-v2

# reconcile photos (always dry-run first!)
python skills/photo-reconciler/scripts/reconcile.py --work D:/scratch index-icloud
python skills/photo-reconciler/scripts/reconcile.py --work D:/scratch index-google ./extracted
python skills/photo-reconciler/scripts/reconcile.py --work D:/scratch compare
python skills/photo-reconciler/scripts/reconcile.py --work D:/scratch stage --dry-run --list D:/scratch/unique_images.txt
```

See each tool's `SKILL.md` for the full runbook and the hard-won gotchas.

## Layout
```
sidequests/
├─ .claude-plugin/{plugin.json, marketplace.json}
└─ skills/
   ├─ photo-reconciler/  SKILL.md + scripts/reconcile.py + requirements.txt
   └─ source-finder/     SKILL.md + scripts/{extract_audio,fingerprint,transcribe,separate_vocals,frames}.py
```

## License
MIT — see [LICENSE](LICENSE).
