#!/usr/bin/env python3
"""copy_scan.py - find long helper / caption / subtitle text in HTML so it can be cut to a few words.

Walks HTML files with the stdlib parser and reports every "helper-ish" element whose visible text is
longer than --max-words: elements whose class names a helper role (sub, subtitle, note, hint, help,
caption, desc, description, muted, lead, tagline, explainer, blurb, intro, helper, small-print),
plus <small>, <figcaption> and <legend>. Text that sits behind an opt-in disclosure is skipped on
purpose -- <details>, [popover], role="tooltip", <template> -- because that is where a longer
explanation is allowed to live. Dialog and modal text IS scanned: it is on screen the moment the
dialog opens.

Usage:
  python copy_scan.py site/                       # every *.html under site/, default 12 words
  python copy_scan.py index.html about.html --max-words 8
  python copy_scan.py site/ --json                # for a script / a checklist
  python copy_scan.py site/ --classes card-sub,why
Exit code: 0 = nothing over budget, 1 = candidates found.

It only FINDS candidates; deciding what to cut is a judgment call (see SKILL.md). Copy generated in
JavaScript (template strings, textContent assignments) is not seen -- grep for it separately.
"""
import argparse
import html.parser
import io
import json
import os
import re
import sys

HELPER_CLASSES = {"sub", "subtitle", "subhead", "note", "notes", "hint", "help", "helper", "help-text",
                  "caption", "desc", "description", "muted", "lead", "tagline", "explainer", "blurb",
                  "intro", "small-print", "fine-print", "secondary", "meta-text", "tip", "subtext"}
HELPER_TAGS = {"small", "figcaption", "legend"}
OPT_IN_TAGS = {"details", "template", "script", "style", "noscript"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Scanner(html.parser.HTMLParser):
    def __init__(self, path, classes):
        super().__init__(convert_charrefs=True)
        self.path, self.classes = path, classes
        self.stack = []          # [tag, is_opt_in, capture_index_or_None]
        self.captures = []       # {line, tag, cls, text}
        self.hits = []

    def _opt_in(self, tag, attrs):
        a = dict(attrs)
        return tag in OPT_IN_TAGS or "popover" in a or (a.get("role") or "").lower() == "tooltip"

    def _helper(self, tag, attrs):
        cls = (dict(attrs).get("class") or "").lower().split()
        named = [c for c in cls if c in self.classes or any(c.endswith("-" + h) or c.startswith(h + "-")
                                                            for h in self.classes)]
        if tag in HELPER_TAGS or named:
            return " ".join(named) or tag
        return None

    def handle_starttag(self, tag, attrs):
        if tag in VOID:
            return
        opt = self._opt_in(tag, attrs) or any(s[1] for s in self.stack)
        cap = None
        if not opt and not any(s[2] is not None for s in self.stack):   # outermost helper only
            role = self._helper(tag, attrs)
            if role:
                cap = len(self.captures)
                self.captures.append({"line": self.getpos()[0], "tag": tag, "cls": role, "text": []})
        self.stack.append([tag, opt, cap])

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):        # tolerate unclosed inner tags
            if self.stack[i][0] == tag:
                for t, _opt, cap in self.stack[i:][::-1]:
                    if cap is not None:
                        self._finish(self.captures[cap])
                del self.stack[i:]
                return

    def handle_data(self, data):
        if any(s[1] for s in self.stack):
            return
        for s in self.stack:
            if s[2] is not None:
                self.captures[s[2]]["text"].append(data)
                return

    def _finish(self, c):
        text = re.sub(r"\s+", " ", "".join(c["text"])).strip()
        c["text"] = text
        c["words"] = len(re.findall(r"[^\s]+", text))
        self.hits.append(c)


def scan_file(path, max_words, classes):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    s = Scanner(path, classes)
    s.feed(src)
    s.close()
    return [dict(h, file=path) for h in s.hits if h["words"] > max_words]


def iter_files(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "dist", "build", "vendor")]
                for fn in sorted(files):
                    if fn.lower().endswith((".html", ".htm")):
                        yield os.path.join(root, fn)
        else:
            yield p


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find long helper/caption text in HTML.")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--max-words", type=int, default=12)
    ap.add_argument("--classes", default="", help="extra helper class names, comma separated")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    classes = HELPER_CLASSES | {c.strip().lower() for c in a.classes.split(",") if c.strip()}
    hits = []
    for path in iter_files(a.paths):
        hits.extend(scan_file(path, a.max_words, classes))
    hits.sort(key=lambda h: -h["words"])
    if a.json:
        print(json.dumps(hits, indent=2, ensure_ascii=False))
    else:
        for h in hits:
            print("%s:%d  <%s .%s>  %d words\n    %s" % (h["file"], h["line"], h["tag"], h["cls"], h["words"],
                                                    h["text"][:220]))
        print("\n%d candidate(s) over %d words" % (len(hits), a.max_words))
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
