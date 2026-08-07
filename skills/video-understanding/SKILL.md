---
name: video-understanding
description: >-
  Give the agent eyes on a video — local file or URL. Probe it, find its
  structure (scene cuts, black frames, freezes, silence), spend a frame budget
  where the picture actually changes, read the stills, and pull captions/audio
  with their provenance labeled. Use when the user shares a video or YouTube
  link and asks what happens in it, what's on screen at some moment, "watch
  this", "summarize this video", "what does the error say in this recording",
  or when another skill needs on-screen text as ground truth.
allowed-tools: Bash, Read, Write, WebSearch, WebFetch
argument-hint: "<video path or URL> [what you want to know]"
---

# Video understanding — perceive, then interpret

A video is not a document. You cannot "read" it; you can only sample it. Every
mistake in this skill comes from sampling badly and then reasoning confidently
about what you never actually looked at.

Two engines, same method:

| | When | Cost |
|---|---|---|
| **`claude-video-vision` plugin** (jordanrendric) | Installed and ffmpeg is on PATH. Gives you MCP tools `video_watch` / `video_analyze` / `video_detail` / `video_info`, frames returned inline as images, plus audio transcription via Gemini / local Whisper / OpenAI. | Node 20+, ffmpeg **and ffprobe** on PATH, an audio backend |
| **`scripts/videoscan.py`** (bundled here) | Anywhere. Same method, no Node, no ffprobe, no API key — writes stills to disk and you `Read` them. | `pip install -r requirements.txt` |

Prefer the plugin when it's there — native audio understanding (it hears
non-speech events, not just words) is the part the script can't match. Use
`videoscan.py` when it isn't, or when a skill must work on a bare machine.

Install the plugin (run these **one at a time** in Claude Code):

```
/plugin marketplace add https://github.com/jordanrendric/claude-video-vision
/plugin install claude-video-vision
/claude-video-vision:setup-video-vision
```

On Windows it needs a real ffmpeg on PATH (`winget install Gyan.FFmpeg`) —
`imageio-ffmpeg`'s bundled binary is not on PATH and ships no `ffprobe`, which
is why `videoscan.py` deliberately parses `ffmpeg -i` stderr instead.

## Hard rules

1. **Structure before frames.** Never sample evenly and hope. `analyze` first:
   a 40-minute screen recording is 3 things happening and 37 minutes of a
   static cursor. Evenly-spaced frames spend the whole budget on the cursor.
2. **Frames are ground truth; captions are hearsay.** On-screen text — HUD
   banners, terminal output, title cards, menus — is what the software actually
   did. Auto-captions are a guess about a sound. When they disagree, the frame
   wins.
3. **Budget the frames.** Each still costs real context (~1–1.5k tokens).
   8–12 well-chosen frames beat 60 evenly-spaced ones and leave room to think.
   Go back for more with `--times` once you know where to look.
4. **Say which second you saw.** Every claim about a video cites a timestamp.
   "The build fails" is worthless; "at 04:12 the terminal shows
   `ENOENT: tsconfig.json`" is a finding. The filenames carry the timestamp
   (`f_00041200.jpg` = 412.00 s) and `frames.json` maps them explicitly.
5. **Never claim you watched what you sampled.** You saw N stills. If the
   answer depends on motion between them (did the click land? did it stutter?),
   sample denser there or say you can't tell.

## Pipeline

```bash
pip install -r ${CLAUDE_SKILL_DIR}/requirements.txt      # once
VS="${CLAUDE_SKILL_DIR}/scripts/videoscan.py"
```

### 1. Probe — is it what you think it is?
```bash
python "$VS" probe clip.mp4          # or a YouTube/any URL
```
Duration, resolution, fps, audio present, and a `suggested_fps` for whole-video
coverage. URLs are **stream-seeked** via yt-dlp — a 75-minute video is sampled
in seconds, never downloaded.

### 2. Analyze — where does the picture change?
```bash
python "$VS" analyze clip.mp4 --filters scene,black,silence,motion
```
Scene cuts (with scores), black stretches (chapter breaks, fades, dropped
signal), freezes (a hung UI, a dropped stream), silence (the boundaries of what
was said), and an SI/TI motion profile that tells you whether you're looking at
slides or at gameplay. On a URL this streams the whole file — bound it with
`--start/--duration`.

### 3. Plan — spend the budget
```bash
python "$VS" plan clip.mp4 --budget 9
```
Cuts first (landing ~0.6 s *after* each cut, inside the new shot — land on the
cut itself and you get the dissolve), then even fill so static stretches still
get one look.

### 4. Extract, then Read every still
```bash
python "$VS" frames clip.mp4 --scenes --budget 9            # scene-aware
python "$VS" frames clip.mp4 --times 15,1:40,930 --scale 768
python "$VS" frames clip.mp4 --times 412 --crop chat --zoom 3   # legible small text
```
Regions: `left right top bottom center topleft topright bottomleft bottomright
hud chat` or `x,y,w,h` fractions. `--zoom` upscales before writing, which is how
you read a chat column or a status bar; `--format png` keeps UI text lossless
for screen recordings. Then **Read the files** — that is the actual perception
step, and the only one that produces evidence.

### 5. Audio, when the words matter
```bash
python "$VS" subs "https://youtu.be/ID"     # captions + provenance label
python "$VS" audio clip.mp4 --out _a.wav --start 4:00 --duration 60
```
`subs` tries **manual subtitles first, auto-captions second, and tells you
which you got** — manual is authored text, auto is a speech model's guess, and
you should weigh them differently. Rolling-window duplicate lines are collapsed.
For local files (or when captions are missing) `audio` gives you a 16 kHz mono
wav to hand to Whisper (`source-finder/scripts/transcribe.py`) or to a
fingerprinter.

## Validate the toolchain
```bash
python ${CLAUDE_SKILL_DIR}/scripts/selftest.py
python ${CLAUDE_SKILL_DIR}/scripts/selftest.py --url "https://youtu.be/jNQXAC9IVRw"
```
Builds a synthetic clip with cuts at 5/10/15 s, a black stretch, and a silent
window, then asserts videoscan finds all of it. Run it before trusting the
skill on a new machine — it fails loudly on a missing ffmpeg, a broken yt-dlp,
or a stale Python.

## Gotchas (each one cost a debugging session)

- **`--sub-langs "en.*"` fans out.** It matches YouTube's machine-*translated*
  tracks (`en-de`, `en-fr`, …) — dozens of requests, then HTTP 429. Use `en`.
- **`--convert-subs` needs a PATH ffmpeg** and fails silently to a `.vtt`
  without one. `videoscan.py` parses VTT directly instead.
- **No-commentary footage lies in captions.** Auto-captions of a silent
  walkthrough transcribe in-game battle voice lines ("fire and ice!"). A step
  sequence reconstructed from them is fabrication. Read frames.
- **Metadata sinks explode.** `metadata=mode=print` after a raw `scdet` writes
  one entry per decoded frame. Put `select=gt(scene\,TH)` in front of it, and
  keep `blackdetect`/`freezedetect` *upstream* of the select so they still see
  every frame.
- **Windows paths break lavfi twice** — the drive-letter colon and the
  backslashes. `videoscan.py` normalizes both.
- **yt-dlp without a JS runtime** drops the good formats with a warning and
  falls back to 360p. Fine for reading a HUD; install `deno` if you need 720p.
- **`-ss` before `-i` is the fast seek** (range requests on URLs). After `-i`
  it decodes from zero and a long video takes minutes instead of a second.

## Where else this shows up
`game-walkthrough` (read a quest video's objective banners), `source-finder`
(on-screen clues before audio ID), `bugfix` (a screen-recorded repro),
`two-agent-build-test-loop` (video as runtime evidence). Those skills ship
byte-identical copies of `videoscan.py`; after editing this one, run
`python ${CLAUDE_SKILL_DIR}/scripts/checksync.py --fix` from the repo root.
