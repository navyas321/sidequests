"""journal.py: keep a per-machine (or per-device) config journal repo. Stdlib only.

  python journal.py init REPO --title "Gaming PC config" [--about "one line on the machine's role"]
  python journal.py add REPO --title "Wi-Fi stutter: roaming + orphaned services" \
      --summary "Roaming aggressiveness to Lowest; orphaned vendor services disabled" \
      [--date 2026-11-18] [--kind change|analysis|runbook]

`add` writes docs/<date>-<slug>.md from the template (what/why, before-state, steps, verified,
reversal, ruled out, follow-ups, amendments) and adds a row to the README's change log (or a link
under Analyses / Rebuild runbooks). It never overwrites an existing doc.
"""
import argparse
import datetime as dt
import os
import re
import sys

README_TMPL = """# {title}

A running log of intentional changes made to this machine: what changed, **why**, how to
**reverse** it, and follow-ups suggested but not applied. Any future session, human or agent,
should be able to see the state the machine was put in and undo anything cleanly.

## Machine

- {about}

## Change log

| Date | Change | Status |
|------|--------|--------|

## Analyses

Point-in-time measurements. Not changes, so no reversal applies.

## Rebuild runbooks

Forward-looking: point a fresh session at one and it can rebuild that subsystem on another host.

## Guiding rules

- **Reversible by default:** disable, don't uninstall or delete, unless explicitly asked.
- **Never touch** the things this machine exists for (list them here), without the owner's say-so.
- Every applied change records a one-line reversal.
- Capture the before-state as an artifact (command output in the doc), not just prose.
- No secrets: no passwords, tokens, license keys or recovery codes, even in a private repo.
"""

DOC_TMPL = """# {title} ({date})

{summary}

Status: **{status}**.

## Before

<!-- Command output captured BEFORE any change: versions, settings, service states, sizes. -->

## What was done

<!-- Exact commands or UI steps, in order. -->

## Verified

<!-- What was observed afterwards, with the command that shows it. Say what was NOT verified. -->

## Reversal

<!-- The exact commands that put things back. -->

## Ruled out

<!-- Checked and cleared, with evidence, so the next session doesn't chase it again. -->

## Suggested follow-ups (not applied)

| Suggestion | Why |
|---|---|

## Amendments after review

<!-- Corrections from an independent review, with severity. Never silently rewrite history. -->
"""

SECTION = {"change": "## Change log", "analysis": "## Analyses", "runbook": "## Rebuild runbooks"}


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:60].rstrip("-") or "entry"


def _write(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def init(repo, title, about):
    os.makedirs(os.path.join(repo, "docs"), exist_ok=True)
    readme = os.path.join(repo, "README.md")
    if os.path.exists(readme):
        raise SystemExit("README.md already exists in %s" % repo)
    _write(readme, README_TMPL.format(title=title, about=about or "Role, OS, key hardware."))
    return readme


def add_to_readme(text, kind, date, title, summary, rel):
    lines = text.split("\n")
    head = SECTION[kind]
    try:
        start = lines.index(head)
    except ValueError:
        lines += ["", head, ""]
        start = len(lines) - 2
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    if kind == "change":
        row = "| %s | [%s](%s): %s | Applied |" % (date, title.replace("|", "/"), rel, summary.replace("|", "/"))
        last_row = max((i for i in range(start, end) if lines[i].startswith("|")), default=None)
        if last_row is None:
            lines[start + 1:start + 1] = ["", "| Date | Change | Status |", "|------|--------|--------|", row]
        else:
            lines.insert(last_row + 1, row)
    else:
        item = "- [`%s`](%s): %s" % (rel, rel, summary)
        insert_at = end
        while insert_at > start + 1 and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        lines[insert_at:insert_at] = [item] if lines[insert_at - 1].startswith("- ") else ["", item]
    return "\n".join(lines)


def add(repo, title, summary, date=None, kind="change"):
    date = date or dt.date.today().isoformat()
    readme = os.path.join(repo, "README.md")
    if not os.path.exists(readme):
        raise SystemExit("no README.md in %s; run `journal.py init` first (or check the path)" % repo)
    rel = "docs/%s-%s.md" % (date, slugify(title))
    path = os.path.join(repo, *rel.split("/"))
    if os.path.exists(path):
        raise SystemExit("%s already exists; edit it instead" % rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    status = {"change": "Applied", "analysis": "Analysis (no change made)", "runbook": "Runbook"}[kind]
    _write(path, DOC_TMPL.format(title=title, date=date, summary=summary, status=status))
    with open(readme, encoding="utf-8") as f:
        text = f.read()
    _write(readme, add_to_readme(text, kind, date, title, summary, rel))
    return rel


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("repo")
    i.add_argument("--title", required=True)
    i.add_argument("--about", default="")
    a = sub.add_parser("add")
    a.add_argument("repo")
    a.add_argument("--title", required=True)
    a.add_argument("--summary", required=True)
    a.add_argument("--date")
    a.add_argument("--kind", choices=sorted(SECTION), default="change")
    args = ap.parse_args(argv)
    if args.cmd == "init":
        print("wrote", init(args.repo, args.title, args.about))
    else:
        print("wrote", add(args.repo, args.title, args.summary, args.date, args.kind))
    return 0


if __name__ == "__main__":
    sys.exit(main())
