#!/usr/bin/env python3
"""Extract HUD-readable frames from a walkthrough video WITHOUT downloading it.

Stream-seeks the video via yt-dlp's direct URL + ffmpeg HTTP range requests,
so sampling a 75-minute video costs seconds. Frames land in _gwframes/ as
f_<seconds>.jpg for the agent to Read (objective banners, area titles, menus).

Usage:
  python vidframes.py <url> --auto 9              # 9 frames spread over duration
  python vidframes.py <url> --times 15,40,65,300  # explicit seconds
"""
import argparse
import os
import subprocess
import sys


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"  # hope it's on PATH


def ytdlp(*args: str) -> str:
    out = subprocess.run(
        [sys.executable, "-m", "yt_dlp", *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode != 0:
        sys.exit(f"yt-dlp failed: {out.stderr.strip()[:500]}")
    return out.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--auto", type=int, default=0, help="N frames spread across the video")
    ap.add_argument("--times", default="", help="comma-separated seconds")
    ap.add_argument("--outdir", default="_gwframes")
    args = ap.parse_args()

    times: list[int] = []
    if args.times:
        times = [int(t) for t in args.times.split(",") if t.strip()]
    if args.auto:
        dur = int(float(ytdlp("--print", "duration", "--skip-download", args.url).splitlines()[-1]))
        step = dur // (args.auto + 1)
        times += [step * (i + 1) for i in range(args.auto)]
    if not times:
        sys.exit("give --auto N or --times a,b,c")

    # 720p-with-audio (22) > best mp4 video-only <=720p > 360p (18); single
    # file formats only, so no ffmpeg merge is needed.
    stream = ytdlp("-g", "-f", "22/bv*[height<=720][ext=mp4]/18", args.url).splitlines()[0]
    os.makedirs(args.outdir, exist_ok=True)
    ff = ffmpeg_exe()
    for t in sorted(set(times)):
        dst = os.path.join(args.outdir, f"f_{t}.jpg")
        r = subprocess.run(
            [ff, "-hide_banner", "-loglevel", "error", "-ss", str(t),
             "-i", stream, "-frames:v", "1", "-q:v", "2", dst, "-y"],
            capture_output=True, text=True,
        )
        print(f"{'ok ' if r.returncode == 0 and os.path.exists(dst) else 'ERR'} {dst}")


if __name__ == "__main__":
    main()
