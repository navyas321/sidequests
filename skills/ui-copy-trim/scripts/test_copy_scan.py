#!/usr/bin/env python
"""Tests for copy_scan.py. Pure stdlib: python test_copy_scan.py"""
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import copy_scan as C  # noqa: E402

LONG = ("Snap or pick up to twenty cards. Each photo is read, categorized, and shown below to review "
        "before anything is saved. Images are processed then deleted and never stored.")

PAGE = """<!doctype html><html><body>
<h1>Cards</h1>
<p class="sub">%s</p>
<p class="sub">Up to 20 cards. Review before saving.</p>
<div class="card"><p>%s</p></div>
<details><summary>How it works</summary><p class="note">%s</p></details>
<div popover id="why"><p class="hint">%s</p></div>
<div class="modal" role="dialog"><h2>Restore</h2><p class="sub">%s</p></div>
<small>%s <a href="#">link text</a></small>
<p class="card-sub">%s</p>
</body></html>""" % (LONG, LONG, LONG, LONG, LONG, LONG, LONG)


class Scan(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.f = os.path.join(self.d, "page.html")
        with io.open(self.f, "w", encoding="utf-8") as fh:
            fh.write(PAGE)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def hits(self, **kw):
        return C.scan_file(self.f, kw.get("max_words", 12), C.HELPER_CLASSES)

    def test_finds_long_helpers_and_skips_short_ones(self):
        lines = sorted(h["line"] for h in self.hits())
        self.assertEqual(lines, [3, 8, 9, 10])        # sub, modal sub, small, card-sub

    def test_body_content_is_not_a_helper(self):
        self.assertTrue(all("card" != h["cls"] for h in self.hits()))

    def test_opt_in_disclosures_are_left_alone(self):
        self.assertFalse(any(h["line"] in (6, 7) for h in self.hits()))

    def test_child_text_counts(self):
        small = [h for h in self.hits() if h["tag"] == "small"][0]
        self.assertIn("link text", small["text"])

    def test_budget_is_a_parameter(self):
        self.assertEqual(len(C.scan_file(self.f, 200, C.HELPER_CLASSES)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
