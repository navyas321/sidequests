---
name: source-finder
description: >-
  Identify what song or media is playing in a video or audio clip and output
  the source (artist + title + a link). Use when the user shares an audio/video
  file and asks "what's this song?", "what's playing here?", "find the source",
  or Shazam failed. Handles live covers and un-catalogued originals that
  acoustic fingerprinting can't match, by transcribing lyrics and reading
  on-screen clues.
allowed-tools: Bash, Read, WebSearch, WebFetch
---

# Source finder

Identify the song/media in a clip and return the source. **Acoustic
fingerprinting alone is not enough** — it only matches original studio
recordings, so live covers and un-catalogued originals slip through. This skill
is a *fallback ladder*: climb it until something identifies the source, then
**verify** before answering.

Helper scripts live in `${CLAUDE_SKILL_DIR}/scripts/`. Install deps once:
`pip install -r ${CLAUDE_SKILL_DIR}/requirements.txt` (ffmpeg is bundled via
imageio-ffmpeg — no system install needed).

Work in a scratch dir. Clean up `_*.wav`, `_frames/`, `_demucs_out/` when done.

## The ladder — stop as soon as you have a verified answer

**0. Look at the clip first (cheap, often decisive).**
For video, extract frames and READ them — on-screen text, a title card, a
streamer's name/branding, or a live chat where viewers guess the song are
frequently the fastest answer:
```bash
python ${CLAUDE_SKILL_DIR}/scripts/frames.py "<clip>" --n 6 --crop right
```
Then Read the saved `_frames/*.jpg`. Note any names/guesses but treat chat
guesses as *unverified leads*, not the answer.

**1. Acoustic fingerprint (works for studio originals).**
```bash
python ${CLAUDE_SKILL_DIR}/scripts/extract_audio.py "<clip>" -o _audio.wav --stereo
python ${CLAUDE_SKILL_DIR}/scripts/fingerprint.py _audio.wav
```
If it returns a MATCH, jump to **Verify**. A "no match" is normal for covers/
originals — keep climbing.

**2. Transcribe the lyrics (works for covers — it's the words, not the recording).**
```bash
python ${CLAUDE_SKILL_DIR}/scripts/extract_audio.py "<clip>" -o _eq.wav --eq
python ${CLAUDE_SKILL_DIR}/scripts/transcribe.py _eq.wav --model small
```
- Empty result → the VAD or piano masked the vocals. Re-run; escalate the model
  (`--model medium`, then `--model large-v2`). large-v2 is *much* better on
  lyrics buried under instruments.
- Still garbled → isolate the vocals and retry:
  ```bash
  python ${CLAUDE_SKILL_DIR}/scripts/separate_vocals.py _audio.wav -o _vox.wav   # mid-side, instant
  python ${CLAUDE_SKILL_DIR}/scripts/extract_audio.py _vox.wav -o _vox16.wav
  python ${CLAUDE_SKILL_DIR}/scripts/transcribe.py _vox16.wav --model large-v2
  ```
  (If mid-side isn't clean enough, `separate_vocals.py ... --method demucs`.)

**3. Identify from the lyrics.** Take the *most distinctive, consistent* lines
(compare runs — keep words that repeat across model sizes; drop the garbled
ones) and web-search them in quotes. Expect Whisper to mishear some words, so:
- search a couple of different distinctive phrases, not one long string;
- a Google AI-overview / Shazam lyric snippet that echoes your transcript is a
  strong hit;
- combine with any name/branding seen in the frames (step 0).

## Verify before you answer
Confirm the candidate is right — don't trust a single garbled-lyric hit:
- the title's known lyrics should match your transcript, and
- the on-screen clues (artist/branding/chat) should be consistent.
Then find a canonical link (prefer the official upload) with a YouTube search.

## Output
Report: **"<Title>" by <Artist>**, a link, and one line on *how* you got it
(fingerprint / lyrics+search / on-screen). Note caveats honestly — e.g. "this
is a live cover; the original is …", or "the streamer's own original, which is
why Shazam couldn't match it."

## Gotchas (learned the hard way)
- Don't give `transcribe.py` an `initial_prompt` — it echoes it back.
- Whisper VAD discards singing → keep it off (the script default).
- Chat/visual guesses are leads, not proof — always verify against real lyrics.
- demucs on Windows is finicky (needs `diffq`, `numpy<2`, ffmpeg on PATH, a
  non-TorchCodec torchaudio); mid-side is the reliable default.
