#!/usr/bin/env python
"""Tests for triage_report.py. Pure stdlib: python test_triage_report.py"""
import argparse
import datetime as _dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import triage_report as T  # noqa: E402

NOW = _dt.datetime(2026, 11, 18, 12, 0, tzinfo=_dt.timezone.utc)
ARGS = argparse.Namespace(status_field="status", owner_field="owner",
                          time_fields=["updated", "updatedAt", "created"],
                          orphan_hours=8, paused_days=7, block_days=14, dup_ratio=0.88)


def kinds(items):
    return sorted((f["kind"], f["id"]) for f in T.triage(items, NOW, ARGS))


class Triage(unittest.TestCase):
    def test_orphan_needs_age(self):
        old = {"id": "A", "title": "x", "status": "inprogress", "owner": "s1", "updated": "2026-11-10T00:00:00"}
        fresh = dict(old, id="B", title="another thing", updated="2026-11-18T10:00:00")
        self.assertEqual(kinds([old, fresh]), [("orphan", "A")])

    def test_comment_activity_counts_as_alive(self):
        it = {"id": "A", "title": "x", "status": "inprogress", "owner": "s1", "updated": "2026-11-01",
              "comments": [{"at": "2026-11-18T09:00:00", "text": "still on it"}]}
        self.assertEqual(kinds([it]), [])

    def test_paused_without_owner_or_resume_condition(self):
        bare = {"id": "P", "title": "x", "status": "paused", "updated": "2026-11-18"}
        kept = {"id": "Q", "title": "y", "status": "paused", "owner": "s2", "updated": "2026-11-18",
                "detail": "waiting for the vendor fix; resume when 2.1 ships"}
        self.assertEqual(kinds([bare, kept]), [("paused-pile", "P")])

    def test_risk_ok_without_a_risk_is_a_dismissal(self):
        dismissal = {"id": "R1", "title": "Old widget", "status": "accepted",
                     "resolution": "Not worth building right now; low value, verified nobody uses it."}
        real = {"id": "R2", "title": "Public bucket", "status": "accepted",
                "resolution": "Accepted exposure: the bucket only holds public assets; verified the listing."}
        self.assertEqual(kinds([dismissal, real]), [("risk-ok", "R1")])

    def test_stale_blocker(self):
        it = {"id": "S", "title": "Upgrade lib", "status": "open", "detail": "blocked on upstream release",
              "updated": "2026-09-01"}
        self.assertEqual(kinds([it]), [("stale-block", "S")])

    def test_close_without_evidence(self):
        it = {"id": "D", "title": "x", "status": "done", "resolution": "done"}
        ok = {"id": "E", "title": "y", "status": "done",
              "resolution": "Shipped the export button; verified with curl /api/export 200 and a test run."}
        self.assertEqual(kinds([it, ok]), [("no-evidence", "D")])

    def test_duplicate_titles_ignore_type_prefix(self):
        a = {"id": "X", "title": "Task: Fix the login redirect loop", "status": "open", "updated": "2026-11-18"}
        b = {"id": "Y", "title": "Fix login redirect loop", "status": "open", "updated": "2026-11-18"}
        self.assertEqual(kinds([a, b]), [("dup?", "X")])


if __name__ == "__main__":
    unittest.main(verbosity=1)
