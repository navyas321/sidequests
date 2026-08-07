#!/usr/bin/env python3
"""videoscan.py - give an agent eyes on a video: probe, analyze, extract, caption.

CANONICAL COPY: sidequests/skills/video-understanding/scripts/videoscan.py
game-walkthrough/ and source-finder/ ship byte-identical copies. Keep in sync
(`python skills/video-understanding/scripts/checksync.py`).

This is a PERCEPTION layer, not an interpretation layer. It never decides what a
video means - it hands back metadata, structure (scene cuts / black / freeze /
silence), timestamped stills, and captions. The agent Reads the stills and draws
the conclusions.

Design constraints that matter:
  * LOCAL FILES *and* URLs (YouTube etc). URLs are stream-seeked via yt-dlp's
    direct URL + HTTP range requests - sampling a 75-min video costs seconds,
    not a 700 MB download.
  * ffmpeg BINARY ONLY. No ffprobe (imageio-ffmpeg ships ffmpeg alone, and
    that is the only ffmpeg most of these skills can count on). Metadata is
    parsed out of `ffmpeg -i` stderr.
  * Structure before frames. Sampling evenly wastes the frame budget on static
    stretches and misses the cut you cared about; `analyze`/`plan` spend it
    where the picture actually changes.

Commands
  probe    <src>                     metadata as JSON (duration, res, fps, audio)
  analyze  <src>                     scene cuts / black / freeze / silence / motion
  plan     <src> [--budget N]        scene-aware list of timestamps worth reading
  frames   <src> [--auto N|--times|--scenes|--fps F]   write stills + manifest
  subs     <url>                     captions, labeled manual vs auto-generated
  audio    <src>                     16 kHz mono wav for whisper/fingerprinting

Examples
  python videoscan.py probe clip.mp4
  python videoscan.py plan "https://youtu.be/ID" --budget 9
  python videoscan.py frames clip.mp4 --scenes --scale 768
  python videoscan.py frames "https://youtu.be/ID" --times 15,40,65 --crop chat --zoom 3
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------


def die(msg: str) -> "None":
    sys.exit(f"videoscan: {msg}")


def run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg") or die(
            "no ffmpeg - `pip install imageio-ffmpeg` or put ffmpeg on PATH"
        )


def is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def ytdlp(*args: str) -> str:
    out = run([sys.executable, "-m", "yt_dlp", *args])
    if out.returncode != 0:
        die(f"yt-dlp failed: {out.stderr.strip()[:400]}")
    return out.stdout.strip()


def hms(sec: float) -> str:
    sec = max(0.0, float(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:05.2f}"


def parse_time(v: str) -> float:
    """Accept 90, 1:30, 00:01:30.5."""
    parts = str(v).strip().split(":")
    try:
        secs = 0.0
        for p in parts:
            secs = secs * 60 + float(p)
        return secs
    except ValueError:
        die(f"bad timestamp: {v}")


# --------------------------------------------------------------------------
# source resolution + probing
# --------------------------------------------------------------------------

# 22 = 720p muxed, then best mp4 <=720p, then 18 = 360p. Single-file formats
# only, so ffmpeg never has to merge (and never has to download) anything.
URL_FORMAT = "22/bv*[height<=720][ext=mp4]/18/best[height<=720]"

_DUR = re.compile(r"Duration:\s*(\d+):(\d\d):(\d\d(?:\.\d+)?)")
_VIDEO = re.compile(r"Stream #\d+:\d+.*?: Video:\s*([\w.]+).*?,\s*(\d{2,5})x(\d{2,5})")
_FPS = re.compile(r"(\d+(?:\.\d+)?)\s+(?:fps|tbr)")
_AUDIO = re.compile(r"Stream #\d+:\d+.*?: Audio:\s*([\w.]+)")


def resolve(source: str, height: int = 720) -> dict:
    """Local path -> itself. URL -> a direct stream URL that ffmpeg can seek."""
    if not is_url(source):
        if not os.path.exists(source):
            die(f"no such file: {source}")
        return {"src": source, "source": source, "is_url": False, "title": None}

    fmt = URL_FORMAT if height >= 720 else f"bv*[height<={height}][ext=mp4]/18/worst"
    title = ytdlp("--print", "%(title)s", source).splitlines()[-1:]
    stream = ytdlp("-g", "-f", fmt, source).splitlines()
    if not stream:
        die("yt-dlp returned no stream URL")
    return {
        "src": stream[0],
        "source": source,
        "is_url": True,
        "title": title[0] if title else None,
    }


def probe(res: dict) -> dict:
    """Metadata from `ffmpeg -i` stderr. Works on files and on stream URLs."""
    out = run([ffmpeg_exe(), "-hide_banner", "-i", res["src"]])
    err = out.stderr
    meta = {
        "source": res["source"],
        "is_url": res["is_url"],
        "title": res.get("title"),
        "duration_seconds": None,
        "duration": None,
        "width": None,
        "height": None,
        "fps": None,
        "video_codec": None,
        "audio_codec": None,
        "has_audio": False,
    }
    m = _DUR.search(err)
    if m:
        secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        meta["duration_seconds"] = round(secs, 2)
        meta["duration"] = hms(secs)
    m = _VIDEO.search(err)
    if m:
        meta["video_codec"] = m.group(1)
        meta["width"] = int(m.group(2))
        meta["height"] = int(m.group(3))
        f = _FPS.search(err[m.start() : m.start() + 400])
        if f:
            meta["fps"] = float(f.group(1))
    m = _AUDIO.search(err)
    if m:
        meta["audio_codec"] = m.group(1)
        meta["has_audio"] = True
    if meta["duration_seconds"] is None:
        die(f"could not read the video: {err.strip()[-400:]}")
    meta["suggested_fps"] = auto_fps(meta["duration_seconds"])
    return meta


def auto_fps(duration: float) -> float:
    """Sampling rate that keeps a whole video inside a sane frame budget."""
    if duration < 60:
        return 2.0
    if duration < 300:
        return 1.0
    if duration < 900:
        return 0.5
    if duration < 3600:
        return 0.2
    return 0.1


# --------------------------------------------------------------------------
# structural analysis
# --------------------------------------------------------------------------

FILTERS = ("scene", "black", "freeze", "silence", "motion")


def analyze(res: dict, meta: dict, filters, threshold: float, start: float, dur) -> dict:
    """One ffmpeg pass; detectors log to stderr, scene cuts to a metadata file.

    Filter ORDER matters: blackdetect/freezedetect/siti sit upstream of the
    `select`, so they still see every frame, while only scene-change frames
    reach the metadata sink - which keeps that file tiny instead of one entry
    per decoded frame.
    """
    meta_file = os.path.abspath("_videoscan_scenes.txt")
    vf, af = [], []
    if "black" in filters:
        vf.append("blackdetect=d=0.1:pic_th=0.98:pix_th=0.10")
    if "freeze" in filters:
        vf.append("freezedetect=n=-60dB:d=2")
    if "motion" in filters:
        vf.append("siti=print_summary=1")
    if "scene" in filters:
        vf.append(f"select=gt(scene\\,{threshold})")
        vf.append(f"metadata=mode=print:file={lavfi_path(meta_file)}")
    if "silence" in filters and meta.get("has_audio"):
        af.append("silencedetect=n=-40dB:d=0.5")

    if not vf and not af:
        die("no usable filters selected")

    cmd = [ffmpeg_exe(), "-hide_banner", "-y"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", res["src"]]
    if dur:
        cmd += ["-t", str(dur)]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    if af:
        cmd += ["-af", ",".join(af)]
    else:
        cmd += ["-an"]
    cmd += ["-f", "null", "-"]

    out = run(cmd)
    err = out.stderr
    if out.returncode != 0 and "Output file is empty" not in err:
        die(f"analyze failed: {err.strip()[-400:]}")

    result = {
        "source": res["source"],
        "range": {"start": start, "duration": dur},
        "scene_changes": [],
        "black_intervals": [],
        "freeze_intervals": [],
        "silence_intervals": [],
    }

    if "scene" in filters and os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        os.remove(meta_file)
        t = None
        for line in content.splitlines():
            m = re.search(r"pts_time:([\d.]+)", line)
            if m:
                t = float(m.group(1)) + start
                continue
            m = re.search(r"lavfi\.scene_score=([\d.]+)", line)
            if m and t is not None:
                result["scene_changes"].append(
                    {"seconds": round(t, 2), "time": hms(t), "score": float(m.group(1))}
                )
                t = None

    for key, pat in (
        ("black_intervals", r"black_start:([\d.]+)\s+black_end:([\d.]+)"),
        ("freeze_intervals", r"freeze_start:\s*([\d.]+)[\s\S]*?freeze_end:\s*([\d.]+)"),
        (
            "silence_intervals",
            r"silence_start:\s*([-\d.]+)[\s\S]*?silence_end:\s*([-\d.]+)",
        ),
    ):
        for m in re.finditer(pat, err):
            a, b = float(m.group(1)) + start, float(m.group(2)) + start
            result[key].append(
                {"start": hms(a), "end": hms(b), "duration": round(b - a, 2)}
            )

    if "motion" in filters:
        si = re.search(r"Spatial Information:\s*\n\s*Average:\s*([\d.]+)", err)
        ti = re.search(r"Temporal Information:\s*\n\s*Average:\s*([\d.]+)", err)
        if si or ti:
            si_v = float(si.group(1)) if si else None
            ti_v = float(ti.group(1)) if ti else None
            result["motion"] = {
                "spatial_avg": si_v,
                "temporal_avg": ti_v,
                "profile": content_profile(si_v, ti_v),
            }
    return result


def lavfi_path(p: str) -> str:
    """lavfi eats `:` and `\\`. C:\\x -> C\\\\:/x, which survives both parser levels."""
    return re.sub(r"^([A-Za-z]):", r"\1\\\\:", p.replace("\\", "/"))


def content_profile(si, ti) -> str:
    def band(v, hi, mid):
        if v is None:
            return "unknown"
        return "high" if v > hi else "moderate" if v > mid else "low"

    s, t = band(si, 50, 25), band(ti, 30, 10)
    hint = {
        ("low", "low"): " (slides, static UI, menus)",
        ("high", "high"): " (busy action)",
        ("low", "high"): " (simple but fast-moving)",
    }.get((s, t), "")
    return f"{s} visual complexity, {t} motion{hint}"


# --------------------------------------------------------------------------
# planning: where the frame budget should go
# --------------------------------------------------------------------------


def plan_times(meta: dict, cuts: list, budget: int, lead: float = 0.6) -> list:
    """Scene cuts first (landing just AFTER the cut, inside the new shot), then
    evenly spaced fill so long static stretches still get looked at."""
    dur = meta["duration_seconds"]
    times = [min(c["seconds"] + lead, dur - 0.1) for c in cuts]
    times = [t for t in times if t >= 0]
    if len(times) > budget:  # keep the strongest cuts, spread across the video
        keep = sorted(cuts, key=lambda c: -c["score"])[:budget]
        times = sorted(min(c["seconds"] + lead, dur - 0.1) for c in keep)
    fill = max(budget - len(times), 0)
    if fill:
        step = dur / (fill + 1)
        for i in range(fill):
            t = step * (i + 1)
            if all(abs(t - x) > step * 0.25 for x in times):
                times.append(t)
    return sorted(round(t, 2) for t in set(times))


# --------------------------------------------------------------------------
# frame extraction
# --------------------------------------------------------------------------

# x, y, w, h as fractions of the frame.
REGIONS = {
    "left": (0.0, 0.0, 0.5, 1.0),
    "right": (0.5, 0.0, 0.5, 1.0),
    "top": (0.0, 0.0, 1.0, 0.5),
    "bottom": (0.0, 0.5, 1.0, 0.5),
    "center": (0.25, 0.25, 0.5, 0.5),
    "topleft": (0.0, 0.0, 0.5, 0.5),
    "topright": (0.5, 0.0, 0.5, 0.5),
    "bottomleft": (0.0, 0.5, 0.5, 0.5),
    "bottomright": (0.5, 0.5, 0.5, 0.5),
    # HUD/objective banners usually live in the upper-left strip
    "hud": (0.0, 0.0, 0.55, 0.3),
    # Twitch/YouTube-live chat column
    "chat": (0.55, 0.1, 0.45, 0.35),
}


def crop_filter(spec: str) -> str:
    if spec in REGIONS:
        x, y, w, h = REGIONS[spec]
    else:
        try:
            x, y, w, h = (float(v) for v in spec.split(","))
        except ValueError:
            die(f"--crop wants a region name {sorted(REGIONS)} or x,y,w,h fractions")
    return f"crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}"


def extract(res: dict, times: list, args) -> list:
    os.makedirs(args.out, exist_ok=True)
    ext = "png" if args.format == "png" else "jpg"
    vf = []
    if args.crop != "none":
        vf.append(crop_filter(args.crop))
    if args.zoom and args.zoom != 1:
        vf.append(f"scale=iw*{args.zoom}:ih*{args.zoom}:flags=lanczos")
    if args.scale:
        vf.append(f"scale={args.scale}:-2:flags=lanczos")

    ff = ffmpeg_exe()
    manifest = []
    for t in times:
        name = f"f_{int(round(t * 100)):08d}.{ext}"
        dst = os.path.join(args.out, name)
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-ss", str(t), "-i", res["src"]]
        if vf:
            cmd += ["-vf", ",".join(vf)]
        cmd += ["-frames:v", "1"]
        if ext == "jpg":
            cmd += ["-q:v", "2"]
        cmd += [dst, "-y"]
        r = run(cmd)
        ok = r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0
        manifest.append(
            {"seconds": t, "time": hms(t), "file": dst.replace("\\", "/"), "ok": ok}
        )
        if not ok:
            manifest[-1]["error"] = r.stderr.strip()[-200:]
    path = os.path.join(args.out, "frames.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            {"source": res["source"], "title": res.get("title"), "frames": manifest},
            fh,
            indent=2,
        )
    return manifest


# --------------------------------------------------------------------------
# captions + audio
# --------------------------------------------------------------------------


def subs(url: str, lang: str, outdir: str) -> dict:
    """Manual subtitles beat auto-captions; the caller needs to know which it got.

    Auto-captions are also the classic trap on no-commentary footage: they
    transcribe in-game voice lines, not the steps. Provenance is the point.
    """
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, "subs")
    for provenance, flag in (
        ("manual_subtitles", "--write-subs"),
        ("auto_captions", "--write-auto-subs"),
    ):
        for f in glob.glob(base + "*"):
            os.remove(f)
        # Keep --sub-langs narrow. "en.*" also matches YouTube's machine
        # TRANSLATED tracks (en-de, en-fr, ...) - dozens of downloads and a
        # fast 429. And no --convert-subs: that shells out to a PATH ffmpeg
        # this toolchain deliberately does not require. We parse VTT directly.
        out = run(
            [
                sys.executable, "-m", "yt_dlp", "--skip-download", flag,
                "--sub-langs", lang, "-o", base, url,
            ]
        )
        hits = sorted(glob.glob(base + "*.vtt")) + sorted(glob.glob(base + "*.srt"))
        if hits:
            return {
                "transcription_source": provenance,
                "file": hits[0].replace("\\", "/"),
                "text": captions_text(hits[0]),
            }
        if "HTTP Error 429" in out.stderr:
            die("YouTube rate-limited the caption request (429) - retry later")
    return {"transcription_source": None, "file": None, "text": ""}


def captions_text(path: str) -> str:
    """VTT/SRT -> `MM:SS text`, with auto-caption rolling duplicates collapsed.

    Auto-caption cues re-print the previous line plus the new words, so a naive
    dump reads three times as long as the video actually said.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        blocks = re.split(r"\n\s*\n", fh.read())
    lines, prev = [], ""
    for b in blocks:
        rows = b.splitlines()
        idx = next((i for i, r in enumerate(rows) if "-->" in r), None)
        if idx is None:
            continue
        m = re.match(r"\s*(\d+):(\d\d):(\d\d)[,.](\d+)", rows[idx])
        if not m:
            continue
        body = re.sub(r"<[^>]+>", "", " ".join(rows[idx + 1 :]))
        body = re.sub(r"\s+", " ", body).strip()
        if not body or body == prev or body in prev:
            continue
        shown = body[len(prev) :].strip() if prev and body.startswith(prev) else body
        prev = body
        if not shown:
            continue
        t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        lines.append(f"{t // 60:02d}:{t % 60:02d} {shown}")
    return "\n".join(lines)


def audio(res: dict, out: str, start: float, dur) -> str:
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", res["src"]]
    if dur:
        cmd += ["-t", str(dur)]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", out, "-y"]
    r = run(cmd)
    if r.returncode != 0 or not os.path.exists(out):
        die(f"audio extraction failed: {r.stderr.strip()[-300:]}")
    return out


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def add_common(p):
    p.add_argument("source", help="local video path or URL")
    p.add_argument("--height", type=int, default=720, help="max height for URL streams")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("probe", help="metadata as JSON")
    add_common(p)

    p = sub.add_parser("analyze", help="scene cuts, black/freeze/silence, motion")
    add_common(p)
    p.add_argument("--filters", default="scene,black,silence")
    p.add_argument("--threshold", type=float, default=0.4, help="scene cut 0-1")
    p.add_argument("--start", default="0")
    p.add_argument("--duration", default="")

    p = sub.add_parser("plan", help="scene-aware timestamps worth reading")
    add_common(p)
    p.add_argument("--budget", type=int, default=12)
    p.add_argument("--threshold", type=float, default=0.4)

    p = sub.add_parser("frames", help="write stills + manifest")
    add_common(p)
    p.add_argument("--auto", type=int, default=0, help="N frames spread evenly")
    p.add_argument("--times", default="", help="comma-separated: 15,1:40,90.5")
    p.add_argument("--scenes", action="store_true", help="sample at scene cuts")
    p.add_argument("--fps", type=float, default=0, help="every 1/fps seconds")
    p.add_argument("--budget", type=int, default=12, help="cap for --scenes/--fps")
    p.add_argument("--threshold", type=float, default=0.4)
    p.add_argument("--crop", default="none", help=f"{sorted(REGIONS)} or x,y,w,h")
    p.add_argument("--zoom", type=float, default=1, help="upscale crops for legibility")
    p.add_argument("--scale", type=int, default=0, help="output width, 0 = native")
    p.add_argument("--format", choices=["jpeg", "png"], default="jpeg")
    p.add_argument("--out", default="_frames")

    p = sub.add_parser("subs", help="captions, labeled manual vs auto")
    p.add_argument("source")
    p.add_argument("--lang", default="en")
    p.add_argument("--out", default="_frames")

    p = sub.add_parser("audio", help="16 kHz mono wav")
    add_common(p)
    p.add_argument("--out", default="_audio.wav")
    p.add_argument("--start", default="0")
    p.add_argument("--duration", default="")

    args = ap.parse_args()

    if args.cmd == "subs":
        if not is_url(args.source):
            die("subs needs a URL (local files have no caption track to fetch)")
        print(json.dumps(subs(args.source, args.lang, args.out), indent=2))
        return

    res = resolve(args.source, args.height)

    if args.cmd == "probe":
        print(json.dumps(probe(res), indent=2))
        return

    if args.cmd == "audio":
        start = parse_time(args.start)
        dur = parse_time(args.duration) if args.duration else None
        print(audio(res, args.out, start, dur))
        return

    if args.cmd == "analyze":
        meta = probe(res)
        filters = [f.strip() for f in args.filters.split(",") if f.strip()]
        bad = [f for f in filters if f not in FILTERS]
        if bad:
            die(f"unknown filter(s) {bad}; pick from {list(FILTERS)}")
        if res["is_url"] and not args.duration:
            print(
                "note: analyzing a URL streams the whole video - use --start/--duration"
                " to bound it",
                file=sys.stderr,
            )
        out = analyze(
            res, meta, filters, args.threshold,
            parse_time(args.start), parse_time(args.duration) if args.duration else None,
        )
        out["metadata"] = meta
        print(json.dumps(out, indent=2))
        return

    meta = probe(res)

    if args.cmd == "plan":
        cuts = analyze(res, meta, ["scene"], args.threshold, 0, None)["scene_changes"]
        times = plan_times(meta, cuts, args.budget)
        print(
            json.dumps(
                {
                    "metadata": meta,
                    "scene_changes": len(cuts),
                    "times": times,
                    "command": "videoscan.py frames "
                    f'"{args.source}" --times {",".join(str(t) for t in times)}',
                },
                indent=2,
            )
        )
        return

    # frames
    times = [parse_time(t) for t in args.times.split(",") if t.strip()]
    if args.scenes:
        cuts = analyze(res, meta, ["scene"], args.threshold, 0, None)["scene_changes"]
        times += plan_times(meta, cuts, args.budget)
    if args.fps:
        n = min(int(meta["duration_seconds"] * args.fps), args.budget)
        times += [i / args.fps for i in range(n)]
    if args.auto:
        step = meta["duration_seconds"] / (args.auto + 1)
        times += [step * (i + 1) for i in range(args.auto)]
    if not times:
        die("pick frames: --auto N, --times a,b,c, --scenes, or --fps F")
    times = sorted(set(round(t, 2) for t in times if 0 <= t < meta["duration_seconds"]))

    manifest = extract(res, times, args)
    ok = sum(1 for m in manifest if m["ok"])
    for m in manifest:
        print(f"{'ok ' if m['ok'] else 'ERR'} {m['time']}  {m['file']}")
    print(f"\n{ok}/{len(manifest)} frames -> {args.out}/ (Read them; timestamps above)")
    if ok < len(manifest):
        sys.exit(1)


if __name__ == "__main__":
    main()
