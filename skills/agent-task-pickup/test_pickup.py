#!/usr/bin/env python
"""Regression + gaming-resistance suite for pickup.py. Pure stdlib, headless: python test_pickup.py"""
import os, sys, unittest, datetime as _dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pickup as P  # noqa: E402

NOW = _dt.datetime(2026, 7, 1, 12, 0, 0)


def item(id, priority="medium", type="task", source=None, created="2026-07-01T00:00:00",
         detail="x" * 120, effort=None, epic=None, children=None, status="open"):
    it = {"id": id, "priority": priority, "type": type, "title": "t", "detail": detail,
          "status": status, "created": created}
    for k, v in (("source", source), ("effort", effort), ("epic", epic), ("children", children)):
        if v is not None:
            it[k] = v
    return it


def ids(items, actor="interactive"):
    return [r["id"] for r in P.rank(items, actor=actor, now=NOW)["items"]]


class T(unittest.TestCase):
    def test_band_first_ordering(self):                       # lesson 1
        got = ids([item("L", "low"), item("C", "critical"), item("M", "medium"), item("H", "high")])
        self.assertEqual(got, ["C", "H", "M", "L"])

    def test_critical_beats_small_fresh_high(self):           # lesson 1 (the divisor-inversion case)
        items = [item("HI", "high", type="bug", effort="S", source="user-request"),
                 item("CR", "critical", type="epic", effort="XL", children=list("abcde"))]
        self.assertEqual(ids(items)[0], "CR")

    def test_provenance_allowlist_and_spoof_cap(self):        # lesson 2
        self.assertEqual(P.provenance("user-request")[0], 1.0)
        self.assertEqual(P.provenance("user-2026-06-30")[0], 1.0)
        for spoof in ("userspace-tidy", "user_agent", "user-notreally"):
            self.assertEqual(P.provenance(spoof)[0], 0.3, spoof)

    def test_determinism_across_shuffle(self):                # lesson 3
        base = [item("BL-%03d" % n, "high", type="bug", source="user-request", effort="S")
                for n in (200, 100, 300, 150)]
        self.assertEqual(ids(base), ids(list(reversed(base))))
        self.assertEqual(ids(base), sorted(ids(base)))

    def test_gate_routes_not_drops(self):                     # lessons 4/5
        crit = item("BL-001", "critical", type="bug", source=None, created=None, status="accepted",
                    detail="X-Ask-Claude CSRF header is the only auth")
        out = P.rank([crit], actor="watcher", now=NOW)
        self.assertEqual([g["id"] for g in out["gated"]], ["BL-001"])   # surfaced, not dropped
        self.assertEqual(out["items"], [])                              # never auto-picked
        self.assertIn("BL-001", ids([crit], actor="interactive"))       # interactive bypasses

    def test_gate_triggers(self):                             # lesson 4
        g = lambda it: P.autonomy_gate(it, {})
        self.assertIn("type=", g(item("x", "high", type="epic")) or "")
        self.assertIn("critical", g(item("x", "critical", type="bug")) or "")
        self.assertIn("security-keyword", g(item("x", "high", detail="rotate the csrf token " + "y" * 90)) or "")
        self.assertIn("underspecified", g(item("x", "high", detail="fix it")) or "")
        self.assertIn("file-leased", P.autonomy_gate(
            item("x", "high", detail="edit serve_life.py route " + "z" * 90), {"serve_life.py": "other"}) or "")
        self.assertIsNone(g(item("ok", "high", detail="add a friendly tooltip " + "q" * 90)))

    def test_null_degradation(self):                          # lesson 6
        sc, why = P.score(item("BL-001", "critical", type="bug", source=None, created=None), NOW)
        self.assertIsInstance(sc, float)
        self.assertEqual([w for w in why if w["factor"] == "aging"][0]["value"], 0.0)

    def test_aging_bounded_below_band(self):                  # lesson 7
        items = [item("OLDLOW", "low", source="user-request", effort="S", created="2025-01-01T00:00:00"),
                 item("FRESHCRIT", "critical", type="bug", created="2026-07-01T11:59:00")]
        self.assertEqual(ids(items)[0], "FRESHCRIT")

    def test_small_wins_within_band(self):                    # 'small wins first', size floored
        items = [item("XL", "high", type="bug", effort="XL"), item("S", "high", type="bug", effort="S")]
        self.assertEqual(ids(items), ["S", "XL"])
        self.assertGreaterEqual([w for w in P.score(item("z", "low", effort="S"), NOW)[1]
                                 if w["factor"].startswith("size")][0]["value"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
