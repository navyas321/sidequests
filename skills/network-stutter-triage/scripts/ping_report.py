"""Analyse an interleaved ping CSV (t_ms + one RTT column per target, -1 = lost). Stdlib only.

Per target: loss, p50/p90/p99/max, and "episodes" (runs of consecutive high samples; a run of
--plateau or more samples is a plateau, shorter is a spike). Then the evidence that matters: how
often one target's high samples land on the same pass as another's. If the suspect is high while
the gateway and the other clients are not, the shared network (router, host radio, airtime) is
exonerated and the problem is on the suspect's side of its own link.

usage: python ping_report.py pings.csv [--high-ms 30] [--plateau 3] [--suspect 192.168.1.30] [--json]
"""
import argparse
import csv
import json
import sys


MIN_EVIDENCE = 5  # high samples needed (unless one is a plateau) before clearing the network


def pct(values, p):
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    head = rows[0]
    body = [r for r in rows[1:] if len(r) == len(head)]  # a recorder stopped mid-pass can leave a short last row
    targets = head[1:]
    series = {t: [float(r[i + 1]) for r in body] for i, t in enumerate(targets)}
    return targets, series


def episodes(flags, plateau):
    out, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            n = i - start
            out.append({"start": start, "samples": n, "kind": "plateau" if n >= plateau else "spike"})
            start = None
    return out


def analyse(targets, series, high_ms=30.0, plateau=3, suspect=None):
    n = len(next(iter(series.values()))) if series else 0
    high = {t: [v < 0 or v >= high_ms for v in series[t]] for t in targets}
    per = {}
    for t in targets:
        ok = [v for v in series[t] if v >= 0]
        eps = episodes(high[t], plateau)
        per[t] = {
            "samples": n, "lost": sum(1 for v in series[t] if v < 0),
            "p50": pct(ok, 50), "p90": pct(ok, 90), "p99": pct(ok, 99), "max": max(ok) if ok else None,
            "high": sum(high[t]), "plateaus": sum(1 for e in eps if e["kind"] == "plateau"),
            "spikes": sum(1 for e in eps if e["kind"] == "spike"),
        }
    overlap = {}
    for a in targets:
        for b in targets:
            if a < b:
                both = sum(1 for x, y in zip(high[a], high[b]) if x and y)
                expect = (per[a]["high"] * per[b]["high"] / n) if n else 0
                overlap["%s|%s" % (a, b)] = {"both": both, "chance": round(expect, 2)}
    verdict = None
    if suspect and suspect not in per:
        raise ValueError("--suspect %r is not a column in this CSV (columns: %s)" % (suspect, ", ".join(targets)))
    if suspect:
        others = [t for t in targets if t != suspect]
        s_high = per[suspect]["high"]
        shared = sum(1 for i in range(n) if high[suspect][i] and any(high[o][i] for o in others))
        others_quiet = all(per[o]["high"] <= max(1, n // 100) for o in others)
        if s_high == 0:
            verdict = "suspect never went high in this run: reproduce the symptom while recording"
        elif shared == 0 and others_quiet and s_high < MIN_EVIDENCE and per[suspect]["plateaus"] == 0:
            verdict = ("too little evidence: only %d isolated high sample(s) on %s; record longer, "
                       "ideally while the symptom happens" % (s_high, suspect))
        elif shared == 0 and others_quiet:
            verdict = ("network exonerated: %d high samples on %s, none coincide with the other %d targets, "
                       "which stayed quiet; look at the suspect's own radio/driver/power state" % (s_high, suspect, len(others)))
        elif shared >= s_high * 0.5:
            verdict = ("shared cause likely: %d of %d high samples on %s coincide with another target; "
                       "look at the router, the host radio or airtime" % (shared, s_high, suspect))
        else:
            verdict = ("mixed: %d of %d high samples on %s coincide with another target; "
                       "record longer before concluding" % (shared, s_high, suspect))
    return {"passes": n, "highMs": high_ms, "targets": per, "overlap": overlap, "verdict": verdict}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--high-ms", type=float, default=30.0)
    ap.add_argument("--plateau", type=int, default=3)
    ap.add_argument("--suspect")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    targets, series = load(a.csv)
    try:
        res = analyse(targets, series, a.high_ms, a.plateau, a.suspect)
    except ValueError as e:
        raise SystemExit(str(e))
    if a.json:
        print(json.dumps(res, indent=2))
        return 0
    print("%d passes, high = lost or >= %g ms" % (res["passes"], a.high_ms))
    print("%-18s %5s %6s %6s %6s %6s %5s %8s %6s" % ("target", "lost", "p50", "p90", "p99", "max", "high", "plateaus", "spikes"))
    for t, s in res["targets"].items():
        print("%-18s %5d %6s %6s %6s %6s %5d %8d %6d" % (t, s["lost"], s["p50"], s["p90"], s["p99"], s["max"],
                                                        s["high"], s["plateaus"], s["spikes"]))
    print("coinciding high samples (observed vs expected by chance):")
    for pair, o in res["overlap"].items():
        print("  %-36s %3d  (chance %.2f)" % (pair, o["both"], o["chance"]))
    if res["verdict"]:
        print("VERDICT:", res["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
