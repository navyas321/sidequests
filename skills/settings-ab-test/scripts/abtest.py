"""abtest.py: decide "setting A or setting B?" from repeated runs, with honest statistics. Stdlib only.

Each RUN (one stream, one benchmark pass, one session) is one sample. Frames inside a run are not
independent, so the test compares per-run values between the two settings with an exact
permutation test: every way of splitting the runs into two groups of the same sizes.

  # per-run metrics you already have (columns: run, mode, metric...)
  python abtest.py runs runs.csv [--json]

  # PresentMon CSVs, one file per run; the mode is read from the file name
  python abtest.py presentmon DIR --modes balanced,lowlat [--app game.exe] [--hitch-ms 25] [--json]

Output: per-mode mean of each metric, the difference, the two-sided p-value, and a rough estimate of
runs per mode needed to confirm the observed difference (80% power, alpha 0.05).
"""
import argparse
import csv
import glob
import itertools
import json
import math
import os
import random
import re
import statistics as st
import sys

INTERVAL_COLS = ("MsBetweenDisplayChange", "DisplayedTime", "MsBetweenPresents", "FrameTime")
LATENCY_COLS = ("MsUntilDisplayed", "DisplayLatency")


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def presentmon_run(path, app=None, hitch_ms=25.0, long_ms=33.0):
    """Per-run metrics from one PresentMon CSV."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        # Column case differs by PresentMon version/format (msBetweenDisplayChange vs
        # MsBetweenDisplayChange), so match names case-insensitively and ignore stray spaces.
        rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    apps = {(r.get("application") or r.get("processname") or "").lower() for r in rows}
    if app:
        rows = [r for r in rows if (r.get("application") or r.get("processname") or "").lower() == app.lower()]
    elif len(apps) > 1:
        raise ValueError("%s mixes %d processes (%s); pass --app to pick the game or client"
                         % (path, len(apps), ", ".join(sorted(apps)[:5])))
    if not rows:
        raise ValueError("no frames in %s%s" % (path, " for --app %s" % app if app else ""))
    cols = rows[0].keys()
    icol = next((c.lower() for c in INTERVAL_COLS if c.lower() in cols), None)
    if icol is None:
        raise ValueError("%s has none of %s" % (path, ", ".join(INTERVAL_COLS)))
    lcol = next((c.lower() for c in LATENCY_COLS if c.lower() in cols), None)
    shown, dropped = [], 0
    for r in rows:
        v = _num(r.get(icol))
        is_dropped = r.get("dropped", "0") == "1" or v is None or v <= 0
        if is_dropped:
            dropped += 1
        else:
            shown.append(v)
    secs = sum(shown) / 1000.0
    lat = [x for x in (_num(r.get(lcol)) for r in rows) if x is not None and x > 0] if lcol else []
    out = {
        "frames": len(rows),
        "fps_shown": round(len(shown) / secs, 3) if secs else 0.0,
        "dropped_pct": round(100.0 * dropped / len(rows), 4),
        "hitch_pct": round(100.0 * sum(1 for v in shown if v >= hitch_ms) / max(1, len(shown)), 3),
        "p99_interval_ms": round(pct(shown, 99), 3) if shown else None,
        "long_per_min": round(sum(1 for v in shown if v >= long_ms) / (secs / 60.0), 2) if secs else None,
    }
    if lat:
        out["latency_p50_ms"] = round(pct(lat, 50), 3)
        out["latency_p95_ms"] = round(pct(lat, 95), 3)
    return out


def permutation_p(a, b, max_splits=50000, seed=1):
    """Two-sided permutation p-value for a difference in means: exact when the number of splits is
    at most max_splits, otherwise Monte Carlo with the standard +1 correction (never returns 0)."""
    pooled = list(a) + list(b)
    n, k = len(pooled), len(a)
    observed = abs(st.mean(a) - st.mean(b))
    total = math.comb(n, k)
    sampled = total > max_splits
    if sampled:
        rng = random.Random(seed)
        splits = (rng.sample(range(n), k) for _ in range(max_splits))
    else:
        splits = itertools.combinations(range(n), k)
    extreme = 0
    for idx in splits:
        chosen = set(idx)
        ga = [pooled[i] for i in chosen]
        gb = [pooled[i] for i in range(n) if i not in chosen]
        if abs(st.mean(ga) - st.mean(gb)) >= observed - 1e-12:
            extreme += 1
    if sampled:
        return (extreme + 1) / (max_splits + 1)
    return extreme / total


def min_p(n_a, n_b):
    """Smallest two-sided exact p a design can produce: 2/C(n,k) for equal groups (the observed
    split and its mirror), 1/C(n,k) when the groups differ in size."""
    total = math.comb(n_a + n_b, n_a)
    return (2.0 if n_a == n_b else 1.0) / total


def min_runs_per_mode(alpha=0.05):
    """Smallest equal group size whose best possible exact p is below alpha (4 for 0.05)."""
    n = 2
    while min_p(n, n) >= alpha:
        n += 1
    return n


def runs_needed(a, b):
    """Rough runs per mode for 80% power at alpha 0.05 (normal approximation)."""
    diff = abs(st.mean(a) - st.mean(b))
    if diff == 0 or len(a) < 2 or len(b) < 2:
        return None
    floor = min_runs_per_mode()  # fewer runs can never reach p < 0.05 with this test
    sd = math.sqrt((st.variance(a) + st.variance(b)) / 2.0)
    if sd == 0:
        return max(floor, len(a))
    return max(floor, math.ceil(2 * (1.96 + 0.84) ** 2 * sd ** 2 / diff ** 2))


def compare(runs, mode_a, mode_b):
    """runs: list of {"mode":..., metric: value}. Returns per-metric comparison rows."""
    metrics = sorted({k for r in runs for k in r if k not in ("mode", "run")})
    rows = []
    for m in metrics:
        a = [r[m] for r in runs if r["mode"] == mode_a and r.get(m) is not None]
        b = [r[m] for r in runs if r["mode"] == mode_b and r.get(m) is not None]
        if len(a) < 2 or len(b) < 2:
            continue
        rows.append({"metric": m, mode_a: round(st.mean(a), 4), mode_b: round(st.mean(b), 4),
                     "diff": round(st.mean(a) - st.mean(b), 4), "p": round(permutation_p(a, b), 4),
                     "runsNeeded": runs_needed(a, b), "n": [len(a), len(b)]})
    return rows


def load_runs_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        out = []
        for r in csv.DictReader(f):
            row = {"run": r.get("run"), "mode": r["mode"]}
            for k, v in r.items():
                if k not in ("run", "mode"):
                    row[k] = _num(v)
            out.append(row)
    return out


def mode_of(filename, modes):
    """The mode whose label appears as a whole token in the file name ("03-nogsync.csv" is nogsync,
    not gsync). Returns None when no label or more than one label matches."""
    tokens = set(re.split(r"[^a-z0-9]+", os.path.splitext(filename)[0].lower()))
    hit = [m for m in modes if m.lower() in tokens]
    return hit[0] if len(hit) == 1 else None


def load_presentmon_dir(d, modes, app=None, hitch_ms=25.0, skipped=None):
    """Per-run metrics for every labeled CSV in d. Files that are unlabeled, ambiguous or unreadable
    are skipped and listed in `skipped` as (file, reason) so the caller can report them."""
    runs = []
    skipped = skipped if skipped is not None else []
    for path in sorted(glob.glob(os.path.join(d, "*.csv"))):
        name = os.path.basename(path)
        mode = mode_of(name, modes)
        if mode is None:
            skipped.append((name, "no single mode label in the file name"))
            continue
        try:
            r = presentmon_run(path, app, hitch_ms)
        except ValueError as e:
            skipped.append((name, str(e)))
            continue
        r.update({"run": name, "mode": mode})
        runs.append(r)
    return runs


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("runs")
    r.add_argument("csv")
    r.add_argument("--json", action="store_true")
    p = sub.add_parser("presentmon")
    p.add_argument("dir")
    p.add_argument("--modes", required=True, help="two labels found in the file names, e.g. balanced,lowlat")
    p.add_argument("--app")
    p.add_argument("--hitch-ms", type=float, default=25.0)
    p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "runs":
        runs = load_runs_csv(a.csv)
        modes = sorted({x["mode"] for x in runs})
    else:
        modes = [m.strip() for m in a.modes.split(",") if m.strip()]
        skipped = []
        runs = load_presentmon_dir(a.dir, modes, a.app, a.hitch_ms, skipped)
        for name, why in skipped:
            print("skipped %s: %s" % (name, why))
    if len(modes) != 2:
        raise SystemExit("need exactly two modes, got %s" % modes)
    rows = compare(runs, modes[0], modes[1])
    if a.json:
        print(json.dumps({"runs": runs, "comparison": rows}, indent=2))
        return 0
    counts = {m: sum(1 for x in runs if x["mode"] == m) for m in modes}
    print("runs per mode: %s" % counts)
    print("%-18s %12s %12s %10s %8s %12s" % ("metric", modes[0], modes[1], "diff", "p", "runs needed"))
    for x in rows:
        print("%-18s %12s %12s %10s %8s %12s" % (x["metric"], x[modes[0]], x[modes[1]], x["diff"], x["p"],
                                                  x["runsNeeded"] if x["runsNeeded"] else "-"))
    if all(counts.values()):
        print("smallest p this design can show: %.4f" % min_p(counts[modes[0]], counts[modes[1]]))
    if not rows:
        print("no metric had at least 2 runs in each mode")
    return 0


if __name__ == "__main__":
    sys.exit(main())
