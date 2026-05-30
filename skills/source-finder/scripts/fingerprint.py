#!/usr/bin/env python3
"""
fingerprint.py - Acoustic fingerprint lookup via Shazam (shazamio).

This matches ORIGINAL STUDIO RECORDINGS only. It will usually FAIL for:
  - live performances / piano covers
  - original songs not yet in Shazam's catalog
...which is exactly when you fall through to transcribe.py (lyrics) instead.
A "no match" here is informative, not a dead end.

Usage:  python fingerprint.py audio.wav
Requires: pip install shazamio
"""
import asyncio, sys
import imageio_ffmpeg, pydub
pydub.AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
from shazamio import Shazam

async def main(path):
    sh = Shazam()
    meth = "recognize" if hasattr(sh, "recognize") else "recognize_song"
    try:
        res = await getattr(sh, meth)(path)
    except Exception as e:
        print("ERROR:", type(e).__name__, e); return
    track = res.get("track")
    if track:
        print("MATCH:", track.get("title"), "—", track.get("subtitle"))
    else:
        print("NO MATCH (expected for live covers / un-catalogued originals; "
              "fall through to transcribe.py for lyrics)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: fingerprint.py audio.wav")
    asyncio.run(main(sys.argv[1]))
