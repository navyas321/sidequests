---
name: ui-copy-trim
description: >-
  Cut verbose helper text in a web UI down to a few words: subtitles, captions, hints, notes,
  status lines and empty-state copy that explain more than the reader needs. Finds candidates
  with a stdlib scanner, applies a short rewrite rule, leaves real content and opt-in detail
  alone, then render-checks at phone width in both themes. Use when the user says "too verbose",
  "we want a clean UI", "shorten this text", "less wordy", "scan other pages for long text", or
  sends a screenshot of a paragraph-long caption. Ships copy_scan.py + tests.
allowed-tools: Bash, Read, Grep, Glob, Edit
argument-hint: "<html dir or files> [--max-words N]"
---

# ui-copy-trim

Helper copy grows by accretion: every fix adds a clause explaining itself ("updates by itself when
the data is over 12 minutes old, via a direct API call, no usage cost; tap to refresh now"). On a
phone that becomes three lines of grey text above every card. The reader needs the *outcome*, not
the mechanism.

## 1. Find the candidates

```bash
python scripts/copy_scan.py <site-dir> --max-words 12          # human-readable list, longest first
python scripts/copy_scan.py <site-dir> --json > copy.json      # for a checklist
python scripts/copy_scan.py <site-dir> --classes card-sub,why  # add your project's helper classes
```

The scanner reports helper-ish elements (classes like `sub`, `subtitle`, `note`, `hint`,
`caption`, `muted`, `desc`, plus `<small>`, `<figcaption>`, `<legend>`) whose visible text is over
the budget. It skips text behind an opt-in disclosure (`<details>`, `[popover]`,
`role="tooltip"`) on purpose. It does **not** see copy built in JavaScript, so also grep for it:

```bash
grep -rnE "note:\s*['\"][^'\"]{70,}|textContent\s*=\s*['\"][^'\"]{90,}" --include=*.js --include=*.html .
```

## 2. Decide what to cut (the judgment part)

Trim **interface copy**. Leave **content** alone.

| Trim (UI chrome) | Leave (content / opt-in) |
| --- | --- |
| page subtitles, card captions, hints, status lines | the user's own data, bios, notes, analysis paragraphs |
| "how this works" explanations under a control | text inside `<details>` / an info popover the user opens |
| implementation detail (API names, cache TTLs, ticket ids) | legal or safety lines that must stay (shorten, don't drop) |

## 3. Rewrite rule

1. Keep the **outcome**, drop the mechanism: "Auto-refreshes when stale." not "Updates by itself
   when you open Home and the data is over 12 minutes old (direct API call)".
2. Drop what the UI already shows: no "tap to refresh" next to a Refresh button.
3. No ticket ids, version numbers, dates of benchmarks, or internal component names in UI text.
4. Aim for **3–8 words**; one short sentence max. Fragments are fine.
5. Safety/legal lines get shortened, never removed: "Planning context, not financial advice."
6. Keep the same element and class, so styling and tests that select it still work.

## 4. Verify

- Grep tests and scripts for the old phrases before committing (some tests pin copy).
- Render every changed page at **375×812 in dark and light**: no horizontal scroll, nothing cut
  off that should wrap.
- Overflow checkers can report text that is *correctly* clipped by an ellipsis container
  (`white-space:nowrap; overflow:hidden; text-overflow:ellipsis`) as overflow. Before "fixing",
  confirm in a real browser: `document.documentElement.scrollWidth` equals the viewport, and no
  element extends past it once you ignore elements whose ancestor clips them.

## Gotchas

- A status message assembled in code ("Updated automatically — as of 12:50") is still copy; shorten
  the literal ("Updated · 12:50").
- Don't shorten text that a test or a parser keys on without updating that test.
- One pass per page set, then stop: re-reading the same page invites rewriting real content.

## Origin

Born from a session where a user reviewing a phone dashboard said a three-line refresh note was
"too verbose — we want clean UI" and asked for a scan of other pages. The scan found long captions
on about a dozen pages; cutting them to a few words changed no layout and removed most of the grey
text on screen.
