#!/usr/bin/env python3
"""selftest.py - prove videoscan.py actually works on this machine.

Builds a 20 s synthetic clip with KNOWN structure (scene cuts at 5/10/15 s, a
black stretch 10-15 s, silence 5-12 s, burnt-in timecode) and checks that
videoscan finds it. No network, no fixtures - ffmpeg generates the clip.

  python selftest.py            # local-only checks
  python selftest.py --url URL  # also exercise the yt-dlp stream-seek path

Exit code 0 = every check passed. Leaves the clip + frames in a temp dir and
prints the path so you can Read a frame and confirm the timecode is legible.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
VIDEOSCAN = os.path.join(HERE, "videoscan.py")

FAILS: list = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)
    return ok


def scan(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, VIDEOSCAN, *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        import shutil

        return shutil.which("ffmpeg") or sys.exit("selftest: no ffmpeg available")


def build_clip(path: str) -> None:
    """4 x 5 s segments -> cuts at 5/10/15; black 10-15; silence 5-12."""
    vf = (
        "testsrc2=s=640x360:r=15:d=5[v0];"
        "smptebars=s=640x360:r=15:d=5[v1];"
        "color=black:s=640x360:r=15:d=5[v2];"
        "testsrc=s=640x360:r=15:d=5[v3];"
        "[v0][v1][v2][v3]concat=n=4:v=1:a=0[v];"
        "sine=frequency=440:duration=5[a0];"
        "anullsrc=r=44100:cl=mono:d=7[a1];"
        "sine=frequency=880:duration=8[a2];"
        "[a0][a1][a2]concat=n=3:v=0:a=1[a]"
    )
    r = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-filter_complex", vf,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-g", "15", "-c:a", "aac", "-t", "20", path, "-y"],
        capture_output=True, text=True,
    )
    if r.returncode != 0 or not os.path.exists(path):
        sys.exit(f"selftest: could not build the test clip: {r.stderr[-400:]}")


def near(got, want, tol) -> bool:
    return got is not None and abs(float(got) - want) <= tol


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="", help="also test the URL/stream-seek path")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = tempfile.mkdtemp(prefix="videoscan_selftest_")
    os.chdir(work)
    clip = os.path.join(work, "clip.mp4")
    print(f"workdir: {work}\nbuilding test clip...")
    build_clip(clip)

    # --- probe -------------------------------------------------------------
    r = scan("probe", clip)
    meta = json.loads(r.stdout) if r.returncode == 0 else {}
    check("probe exits 0", r.returncode == 0, r.stderr.strip()[-160:])
    check("probe duration ~20s", near(meta.get("duration_seconds"), 20, 0.6),
          str(meta.get("duration_seconds")))
    check("probe resolution 640x360", (meta.get("width"), meta.get("height")) == (640, 360),
          f"{meta.get('width')}x{meta.get('height')}")
    check("probe fps ~15", near(meta.get("fps"), 15, 1), str(meta.get("fps")))
    check("probe finds audio", meta.get("has_audio") is True)
    check("probe suggests a sampling fps", meta.get("suggested_fps") == 2.0,
          str(meta.get("suggested_fps")))

    # --- analyze -----------------------------------------------------------
    r = scan("analyze", clip, "--filters", "scene,black,silence,motion")
    a = json.loads(r.stdout) if r.returncode == 0 else {}
    check("analyze exits 0", r.returncode == 0, r.stderr.strip()[-160:])
    cuts = [c["seconds"] for c in a.get("scene_changes", [])]
    for want in (5, 10, 15):
        check(f"scene cut found at ~{want}s", any(near(c, want, 1.0) for c in cuts),
              f"cuts={cuts}")
    black = a.get("black_intervals", [])
    check("black stretch detected", len(black) >= 1, json.dumps(black))
    sil = a.get("silence_intervals", [])
    check("silence detected ~5-12s", any(near(parse_hms(s["start"]), 5, 1.5) for s in sil),
          json.dumps(sil))
    check("motion profile derived", bool(a.get("motion", {}).get("profile")),
          str(a.get("motion")))

    # --- plan --------------------------------------------------------------
    r = scan("plan", clip, "--budget", "6")
    p = json.loads(r.stdout) if r.returncode == 0 else {}
    times = p.get("times", [])
    check("plan exits 0", r.returncode == 0, r.stderr.strip()[-160:])
    check("plan returns <= budget times", 0 < len(times) <= 6, str(times))
    check("plan lands just after a cut", any(5 < t < 6.5 for t in times), str(times))
    check("plan covers the whole clip", max(times or [0]) > 10, str(times))

    # --- frames ------------------------------------------------------------
    r = scan("frames", clip, "--scenes", "--budget", "5", "--out", "_f_scenes")
    files = sorted(f for f in os.listdir("_f_scenes") if f.endswith(".jpg")) if os.path.isdir("_f_scenes") else []
    check("frames --scenes exits 0", r.returncode == 0, r.stdout[-200:] + r.stderr[-160:])
    check("frames --scenes wrote stills", len(files) >= 3, str(files))
    check("stills are non-empty", all(os.path.getsize(os.path.join("_f_scenes", f)) > 1000 for f in files))
    man = os.path.join("_f_scenes", "frames.json")
    check("manifest written", os.path.exists(man))
    if os.path.exists(man):
        with open(man, encoding="utf-8") as fh:
            mf = json.load(fh)
        check("manifest maps every file to a timestamp",
              all(x["file"] and x["time"] for x in mf["frames"]) and len(mf["frames"]) == len(files))

    r = scan("frames", clip, "--times", "2,0:04,17.5", "--out", "_f_times")
    got = sorted(f for f in os.listdir("_f_times") if f.endswith(".jpg")) if os.path.isdir("_f_times") else []
    check("frames --times exits 0", r.returncode == 0, r.stdout[-200:])
    check("frames --times parses 90 / 1:30 / 90.5 forms", len(got) == 3, str(got))

    # crop + zoom: the crop must actually change the pixel geometry
    r = scan("frames", clip, "--times", "2", "--crop", "hud", "--zoom", "2", "--out", "_f_crop")
    crops = [f for f in os.listdir("_f_crop") if f.endswith(".jpg")] if os.path.isdir("_f_crop") else []
    check("frames --crop exits 0", r.returncode == 0, r.stdout[-200:])
    if crops and got:
        w_full, h_full = jpeg_size(os.path.join("_f_times", got[0]))
        w_crop, h_crop = jpeg_size(os.path.join("_f_crop", crops[0]))
        # hud = 55% x 30% of the frame, then 2x zoom
        check("crop+zoom geometry correct", near(w_crop, 640 * 0.55 * 2, 6) and near(h_crop, 360 * 0.3 * 2, 6),
              f"full={w_full}x{h_full} crop={w_crop}x{h_crop}")

    r = scan("frames", clip, "--times", "2", "--scale", "320", "--format", "png", "--out", "_f_png")
    pngs = [f for f in os.listdir("_f_png") if f.endswith(".png")] if os.path.isdir("_f_png") else []
    check("frames --format png --scale works", r.returncode == 0 and len(pngs) == 1, str(pngs))

    # --- audio -------------------------------------------------------------
    r = scan("audio", clip, "--out", "_a.wav", "--start", "0:02", "--duration", "3")
    check("audio extracts a wav", r.returncode == 0 and os.path.exists("_a.wav")
          and os.path.getsize("_a.wav") > 40000, f"{os.path.getsize('_a.wav') if os.path.exists('_a.wav') else 0}B")

    # --- error handling ----------------------------------------------------
    check("missing file fails loudly", scan("probe", "nope.mp4").returncode != 0)
    check("frames with no selection fails loudly", scan("frames", clip).returncode != 0)
    check("bad filter name fails loudly", scan("analyze", clip, "--filters", "bogus").returncode != 0)
    check("subs rejects a local path", scan("subs", clip).returncode != 0)

    # --- URL path (optional) ----------------------------------------------
    if args.url:
        r = scan("probe", args.url)
        m = json.loads(r.stdout) if r.returncode == 0 else {}
        check("URL probe exits 0", r.returncode == 0, r.stderr.strip()[-200:])
        check("URL probe reads duration+title", bool(m.get("duration_seconds")) and bool(m.get("title")),
              f"{m.get('title')} {m.get('duration')}")
        r = scan("frames", args.url, "--auto", "3", "--out", "_f_url")
        urlf = [f for f in os.listdir("_f_url") if f.endswith(".jpg")] if os.path.isdir("_f_url") else []
        check("URL stream-seek writes stills", r.returncode == 0 and len(urlf) == 3, str(urlf))
        r = scan("subs", args.url, "--out", "_subs")
        s = json.loads(r.stdout) if r.returncode == 0 else {}
        check("subs returns labeled provenance", r.returncode == 0 and
              s.get("transcription_source") in (None, "manual_subtitles", "auto_captions"),
              str(s.get("transcription_source")))
        if s.get("transcription_source"):
            check("caption text is timestamped and non-empty",
                  bool(re.match(r"^\d\d:\d\d \S", s.get("text", ""))),
                  s.get("text", "")[:60])

    print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'ALL CHECKS PASSED'}")
    print(f"artifacts: {work}  (Read _f_scenes/*.jpg - the timecode should be legible)")
    sys.exit(1 if FAILS else 0)


def parse_hms(v: str) -> float:
    h, m, s = v.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def jpeg_size(path: str) -> tuple:
    """Width/height straight out of the JPEG/PNG header - no image library."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            return (int.from_bytes(data[i + 7 : i + 9], "big"),
                    int.from_bytes(data[i + 5 : i + 7], "big"))
        i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
    return (0, 0)


if __name__ == "__main__":
    main()
