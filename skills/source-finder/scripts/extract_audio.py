#!/usr/bin/env python3
"""
extract_audio.py - Pull audio out of a video/audio file using the ffmpeg
binary bundled with imageio-ffmpeg (no system ffmpeg needed).

Modes:
  default      mono 16 kHz WAV (what Whisper ASR wants)
  --eq         + highpass(200Hz) to cut piano/bass + boost vocal mids +
               dynaudnorm + gain. Use when vocals are buried under instruments.
  --stereo     keep stereo 44.1 kHz (needed for vocal separation / mid-side)
  --start/--dur  extract just a segment (seconds)

Examples:
  python extract_audio.py clip.mov -o audio.wav
  python extract_audio.py clip.mov -o vocals_eq.wav --eq
  python extract_audio.py clip.mov -o stereo.wav --stereo
Requires: pip install imageio-ffmpeg
"""
import argparse, subprocess, sys
import imageio_ffmpeg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default="audio.wav")
    ap.add_argument("--eq", action="store_true", help="boost vocals over instruments")
    ap.add_argument("--stereo", action="store_true", help="stereo 44.1k (for separation)")
    ap.add_argument("--start", type=float, default=None)
    ap.add_argument("--dur", type=float, default=None)
    a = ap.parse_args()

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y"]
    if a.start is not None:
        cmd += ["-ss", str(a.start)]
    if a.dur is not None:
        cmd += ["-t", str(a.dur)]
    cmd += ["-i", a.src, "-vn"]
    if a.stereo:
        cmd += ["-ac", "2", "-ar", "44100"]
    else:
        cmd += ["-ac", "1", "-ar", "16000"]
    if a.eq:
        cmd += ["-af", "highpass=f=200,equalizer=f=1500:width_type=o:width=3:g=8,dynaudnorm,volume=4"]
    cmd += [a.out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr[-800:])
    print("wrote", a.out)

if __name__ == "__main__":
    main()
