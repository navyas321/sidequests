#!/usr/bin/env python3
"""
separate_vocals.py - Isolate vocals from instrumental so the lyrics
transcribe cleanly.

Two methods:
  midside  (default) - center channel = vocals, sides = ambience. Instant,
            only needs librosa+soundfile, and worked great on a live recording
            where the voice is panned center. Try this FIRST.
  demucs   - AI source separation, cleaner but heavy and finicky on Windows
            (needs `pip install demucs diffq "numpy<2"`, ffmpeg on PATH, and a
            torchaudio that isn't the TorchCodec-only nightly). Use if mid-side
            isn't clean enough.

Input must be STEREO (use extract_audio.py --stereo).

Usage:
  python separate_vocals.py stereo.wav -o vocals.wav            # mid-side
  python separate_vocals.py stereo.wav -o vocals.wav --method demucs
Requires (midside): pip install librosa soundfile
"""
import argparse, sys, os

def midside(src, out):
    import librosa, soundfile as sf
    y, sr = librosa.load(src, sr=None, mono=False)
    if y.ndim != 2 or y.shape[0] != 2:
        sys.exit("input is not stereo - re-extract with extract_audio.py --stereo")
    mid = (y[0] + y[1]) / 2.0  # vocals dominant
    sf.write(out, mid, sr)
    print("wrote", out, "(mid-side center channel)")

def demucs(src, out):
    import subprocess, imageio_ffmpeg, shutil, glob
    ffdir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    env = dict(os.environ, PATH=ffdir + os.pathsep + os.environ.get("PATH", ""))
    outdir = "_demucs_out"
    r = subprocess.run([sys.executable, "-m", "demucs", "-n", "mdx_extra_q",
                        "--two-stems=vocals", "--out", outdir, src],
                       env=env, capture_output=True, text=True)
    hits = glob.glob(os.path.join(outdir, "**", "vocals.wav"), recursive=True)
    if not hits:
        sys.exit("demucs produced no output:\n" + r.stderr[-800:])
    shutil.copy(hits[0], out)
    print("wrote", out, "(demucs vocals)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default="vocals.wav")
    ap.add_argument("--method", choices=["midside", "demucs"], default="midside")
    a = ap.parse_args()
    (midside if a.method == "midside" else demucs)(a.src, a.out)

if __name__ == "__main__":
    main()
