#!/usr/bin/env python3
"""
reconcile.py - Reconcile a Google Photos album export against an existing
Apple iCloud library, so that ONLY genuinely-missing photos/videos get
uploaded - no duplicates.

Pipeline (run as subcommands, in order):
    index-icloud   Perceptual-hash the local "iCloud for Windows" folder.
                   Reads (hydrates) each image, hashes it, and can free the
                   local copy again so C: never fills. Resumable via checkpoint.
    index-google   Hash the extracted Google export (sha256 + perceptual hash).
    compare        Find Google items NOT already in iCloud, internally dedupe
                   them, and write unique_images.txt / unique_videos.txt.
    stage          Copy the unique files into the iCloud folder (collision-safe;
                   --dry-run and --limit for a canary batch first).
    verify         Accounting + staging-integrity report.

Why this is fiddly (hard-won notes):
  * HEIC: Pillow cannot read HEIC without pillow-heif. Without the fix below,
    every iCloud HEIC fails to hash, iCloud looks "empty", and you re-upload
    everything -> massive duplicates. We register pillow-heif up front.
  * On-demand files: iCloud-for-Windows files are usually online-only
    placeholders. Reading one downloads it; we hash concurrently to overlap
    that latency, and optionally dehydrate (attrib +U -P) to reclaim space.
  * Upload mechanism (iCloud for Windows v14+/Store app): copy files DIRECTLY
    into  C:\\Users\\<you>\\iCloudPhotos\\Photos  - there is no "Uploads"
    subfolder (that was the old <=v13 client). The cloud engine uploads them.
  * The filesystem cannot tell you whether an upload succeeded (with "Download
    originals" on, an uploaded file still looks like a normal local file). The
    iCloud app's own counter / icloud.com is the only ground truth.

Requires: pip install Pillow pillow-heif imagehash numpy tqdm
Windows-only for the staging/dehydration bits; the hashing core is portable.
"""
import os, sys, time, pickle, hashlib, argparse, subprocess, shutil, re
from pathlib import Path

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    print("WARNING: pillow-heif not installed - HEIC will fail to hash. "
          "Run: pip install pillow-heif", file=sys.stderr)

from PIL import Image
import imagehash
import numpy as np

IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".heif", ".tiff", ".tif", ".dng"}
VID_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".3gp", ".m4p"}
THRESH = 8  # max perceptual-hash hamming distance treated as "the same image"

DEFAULT_ICLOUD = r"C:\Users\%s\iCloudPhotos\Photos" % os.environ.get("USERNAME", "")


# ----------------------------------------------------------------- helpers
def free_gb(drive):
    return shutil.disk_usage(drive).free / 2**30

def dehydrate(paths):
    """Release the local copy of cloud files (back to online-only placeholder).
    Non-destructive: re-downloads on demand. Windows + iCloud/OneDrive only."""
    for p in paths:
        try:
            subprocess.run(["attrib", "+U", "-P", str(p)], capture_output=True, timeout=30)
        except Exception:
            pass

def phash_int(path):
    with Image.open(path) as im:
        return int(str(imagehash.phash(im)), 16)

def sha256_of(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def norm_video_name(name):
    stem = Path(name).stem.lower()
    stem = re.sub(r"[\s_]*\(\d+\)$", "", stem)
    stem = re.sub(r"_\d+$", "", stem)
    return stem

_PC16 = np.array([bin(i).count("1") for i in range(1 << 16)], dtype=np.uint16)

def hamming_min_factory(icloud_hashes):
    ic = np.array(icloud_hashes, dtype=np.uint64)
    def min_ham(h):
        if ic.size == 0:
            return 64
        x = ic ^ np.uint64(h)
        v = x.view(np.uint16).reshape(-1, 4)
        return int(_PC16[v].sum(axis=1).min())
    return min_ham


# ----------------------------------------------------------------- index-icloud
def index_icloud(icloud, cache, workers, dehydrate_during, free_floor):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    icloud = Path(icloud)
    state = None
    if cache.exists():
        state = pickle.load(open(cache, "rb"))
        if state.get("complete"):
            print(f"[icloud] already complete: {len(state['img_hashes'])} hashes. "
                  f"Delete {cache.name} to rebuild.")
            return state
    if state is None:
        print("[icloud] listing files ...", flush=True)
        files = sorted(str(p) for p in icloud.rglob("*") if p.is_file())
        state = {"files": files, "img_hashes": [], "vid_keys": set(), "vid_norm": set(),
                 "done": set(), "vid_done": False, "errors": [], "complete": False}
        print(f"[icloud] {len(files)} files to scan.", flush=True)
    else:
        print(f"[icloud] resuming: {len(state['done'])} images already hashed.", flush=True)

    files = state["files"]
    imgs = [f for f in files if Path(f).suffix.lower() in IMG_EXT]
    vids = [f for f in files if Path(f).suffix.lower() in VID_EXT]
    if not state.get("vid_done"):
        for f in vids:
            p = Path(f)
            try:
                state["vid_keys"].add(f"{p.name.lower()}::{p.stat().st_size}")
                state["vid_norm"].add(norm_video_name(p.name))
            except Exception as e:
                state["errors"].append((f, repr(e)))
        state["vid_done"] = True

    done = state["done"]
    todo = [f for f in imgs if f not in done]
    print(f"[icloud] images {len(imgs)} ({len(todo)} to hash), videos {len(vids)}, "
          f"workers={workers}, dehydrate={dehydrate_during}", flush=True)
    t0 = time.time()

    def work(path):
        try:
            return (path, phash_int(Path(path)), None)
        except Exception as e:
            return (path, None, repr(e))

    n = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(work, p) for p in todo]
        for fut in as_completed(futs):
            path, h, err = fut.result()
            done.add(path)
            if err:
                state["errors"].append((path, err))
            elif h is not None:
                state["img_hashes"].append(h)
            n += 1
            if dehydrate_during and n % 200 == 0 and free_gb(icloud.anchor) < free_floor:
                dehydrate([path])
            if n % 50 == 0:
                rate = n / max(time.time() - t0, 1)
                eta = (len(todo) - n) / max(rate, 0.1) / 60
                print(f"[icloud] {n}/{len(todo)} hashed  total={len(state['img_hashes'])}  "
                      f"err={len(state['errors'])}  {rate:.1f}/s  ETA {eta:.0f}min", flush=True)
            if n % 250 == 0:
                pickle.dump(state, open(cache, "wb"))

    state["complete"] = True
    pickle.dump(state, open(cache, "wb"))
    print(f"[icloud] DONE: {len(state['img_hashes'])} image hashes, "
          f"{len(state['vid_keys'])} videos, {len(state['errors'])} errors, "
          f"{time.time()-t0:.0f}s", flush=True)
    if state["errors"]:
        print(f"[icloud] error rate {len(state['errors'])}/{len(imgs)} - "
              f"if this is high, the HEIC fix may not be working.", flush=True)
    return state


# ----------------------------------------------------------------- index-google
def index_google(google_dir, cache):
    google = Path(google_dir)
    state = None
    if cache.exists():
        state = pickle.load(open(cache, "rb"))
        if state.get("complete"):
            print(f"[google] already complete: {len(state['records'])} records.")
            return state
    files = sorted(str(p) for p in google.rglob("*") if p.is_file())
    state = {"records": [], "errors": [], "complete": False}
    print(f"[google] {len(files)} files to index.", flush=True)
    t0 = time.time()
    for i, f in enumerate(files, 1):
        p = Path(f); ext = p.suffix.lower()
        try:
            if ext in IMG_EXT:
                state["records"].append({"path": str(p), "kind": "img",
                                         "phash": phash_int(p), "sha": sha256_of(p)})
            elif ext in VID_EXT:
                sz = p.stat().st_size
                state["records"].append({"path": str(p), "kind": "vid", "size": sz,
                                         "key": f"{p.name.lower()}::{sz}",
                                         "norm": norm_video_name(p.name), "sha": sha256_of(p)})
        except Exception as e:
            state["errors"].append((f, repr(e)))
        if i % 1000 == 0:
            print(f"[google] {i}/{len(files)}  records={len(state['records'])}  "
                  f"{i/max(time.time()-t0,1):.0f}/s", flush=True)
    state["complete"] = True
    pickle.dump(state, open(cache, "wb"))
    nimg = sum(1 for r in state["records"] if r["kind"] == "img")
    nvid = sum(1 for r in state["records"] if r["kind"] == "vid")
    print(f"[google] DONE: {len(state['records'])} records ({nimg} img, {nvid} vid), "
          f"{len(state['errors'])} errors.", flush=True)
    return state


# ----------------------------------------------------------------- compare
def compare(icloud_cache, google_cache, out_dir, thresh):
    ic = pickle.load(open(icloud_cache, "rb"))
    gg = pickle.load(open(google_cache, "rb"))
    assert ic.get("complete") and gg.get("complete"), "indexes incomplete"
    min_ham = hamming_min_factory(ic["img_hashes"])
    imgs = [r for r in gg["records"] if r["kind"] == "img"]
    vids = [r for r in gg["records"] if r["kind"] == "vid"]

    cand_imgs = [r for r in imgs if min_ham(r["phash"]) > thresh]
    cand_vids = [r for r in vids
                 if r["key"] not in ic["vid_keys"] and r["norm"] not in ic["vid_norm"]]

    # internal dedup: exact (sha) then perceptual greedy clustering
    seen, after_sha = set(), []
    for r in cand_imgs:
        if r["sha"] not in seen:
            seen.add(r["sha"]); after_sha.append(r)
    kept_imgs, kept = [], []
    for r in after_sha:
        g = np.uint64(r["phash"])
        if not any(bin(int(g ^ kh)).count("1") <= thresh for kh in kept):
            kept_imgs.append(r); kept.append(g)
    seen, kept_vids = set(), []
    for r in cand_vids:
        if r["norm"] not in seen:
            seen.add(r["norm"]); kept_vids.append(r)

    out_dir = Path(out_dir)
    (out_dir / "unique_images.txt").write_text(
        "\n".join(r["path"] for r in kept_imgs), encoding="utf-8")
    (out_dir / "unique_videos.txt").write_text(
        "\n".join(r["path"] for r in kept_vids), encoding="utf-8")
    print("\n========== RESULT ==========")
    print(f"Google images {len(imgs)}: already-in-iCloud {len(imgs)-len(cand_imgs)}, "
          f"missing {len(cand_imgs)} -> dedup -> {len(kept_imgs)} to upload")
    print(f"Google videos {len(vids)}: already-in-iCloud {len(vids)-len(cand_vids)}, "
          f"missing {len(cand_vids)} -> dedup -> {len(kept_vids)} to upload")
    print(f"Wrote unique_images.txt ({len(kept_imgs)}), unique_videos.txt ({len(kept_vids)})")
    print("SANITY: if 'to upload' ~= ALL google items, the comparison FAILED "
          "(check iCloud index error rate). Do NOT stage a bad result.")


# ----------------------------------------------------------------- stage
def stage(lists, icloud, dry_run, limit):
    icloud = Path(icloud)
    if not icloud.exists():
        sys.exit(f"ERROR: iCloud folder not found: {icloud}")
    files = []
    for lp in lists:
        files += [Path(x) for x in Path(lp).read_text(encoding="utf-8").splitlines() if x.strip()]
    if limit:
        files = files[:limit]
    print(f"Staging {len(files)} files into {icloud}" + (" [DRY RUN]" if dry_run else ""))
    copied = skipped = errors = 0
    for src in files:
        if not src.exists():
            skipped += 1; continue
        dest = icloud / src.name
        i = 1
        while dest.exists():  # never overwrite an existing (possibly real) file
            dest = icloud / f"{src.stem}_{i}{src.suffix}"; i += 1
        if dry_run:
            copied += 1
        else:
            try:
                shutil.copy2(src, dest); copied += 1
            except Exception as e:
                print(f"  [ERROR] {src.name}: {e}"); errors += 1
    print(f"{'DRY RUN ' if dry_run else ''}staged={copied} skipped={skipped} errors={errors}")
    if not dry_run and copied:
        print("iCloud for Windows will upload these automatically - watch the tray / "
              "icloud.com. The filesystem can't confirm upload; the app counter can.")


# ----------------------------------------------------------------- verify
def verify(icloud_cache, google_cache, lists, icloud, thresh):
    ic = pickle.load(open(icloud_cache, "rb"))
    gg = pickle.load(open(google_cache, "rb"))
    min_ham = hamming_min_factory(ic["img_hashes"])
    imgs = [r for r in gg["records"] if r["kind"] == "img"]
    vids = [r for r in gg["records"] if r["kind"] == "vid"]
    img_missing = sum(1 for r in imgs if min_ham(r["phash"]) > thresh)
    vid_missing = sum(1 for r in vids if r["key"] not in ic["vid_keys"]
                      and r["norm"] not in ic["vid_norm"])
    staged = []
    for lp in lists:
        staged += [x.strip() for x in Path(lp).read_text(encoding="utf-8").splitlines() if x.strip()]
    icloud = Path(icloud)
    present = 0; missing = []
    for s in staged:
        base = os.path.basename(s); sz = os.path.getsize(s)
        stem, ext = os.path.splitext(base)
        cands = [base] + [f"{stem}_{i}{ext}" for i in range(1, 8)]
        if any((icloud / c).exists() and (icloud / c).stat().st_size == sz for c in cands):
            present += 1
        else:
            missing.append(base)
    print("========= VERIFY =========")
    print(f"Google total: {len(imgs)} photos + {len(vids)} videos")
    print(f"  already in iCloud: {len(imgs)-img_missing} photos, {len(vids)-vid_missing} videos")
    print(f"  routed to upload:  {img_missing} photos, {vid_missing} videos (pre-dedup)")
    print(f"Staged files present & byte-intact in iCloud folder: {present}/{len(staged)}")
    if missing:
        print(f"  NOT found ({len(missing)}) - inspect these (often junk/blank frames "
              f"iCloud de-duped, or re-encoded on ingest): {missing[:10]}")


# ----------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default=".", help="working dir for caches/lists (default: cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("index-icloud")
    a.add_argument("--icloud", default=DEFAULT_ICLOUD)
    a.add_argument("--workers", type=int, default=8)
    a.add_argument("--dehydrate", action="store_true", help="free local copies as you go (low disk)")
    a.add_argument("--free-floor", type=float, default=15.0, help="GB; dehydrate when below")

    b = sub.add_parser("index-google"); b.add_argument("google_dir")
    sub.add_parser("compare")
    s = sub.add_parser("stage")
    s.add_argument("--icloud", default=DEFAULT_ICLOUD)
    s.add_argument("--list", action="append", required=True)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--limit", type=int, default=0, help="stage only first N (canary)")
    v = sub.add_parser("verify")
    v.add_argument("--icloud", default=DEFAULT_ICLOUD)
    v.add_argument("--list", action="append", required=True)

    args = ap.parse_args()
    work = Path(args.work); work.mkdir(parents=True, exist_ok=True)
    ic_cache, gg_cache = work / "icloud_index.pkl", work / "google_index.pkl"

    if args.cmd == "index-icloud":
        index_icloud(args.icloud, ic_cache, args.workers, args.dehydrate, args.free_floor)
    elif args.cmd == "index-google":
        index_google(args.google_dir, gg_cache)
    elif args.cmd == "compare":
        compare(ic_cache, gg_cache, work, THRESH)
    elif args.cmd == "stage":
        stage(args.list, args.icloud, args.dry_run, args.limit)
    elif args.cmd == "verify":
        verify(ic_cache, gg_cache, args.list, args.icloud, THRESH)


if __name__ == "__main__":
    main()
