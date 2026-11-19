---
name: machine-config-journal
description: >-
  Keep a private git repo per machine or device (a gaming PC, a handheld, a home server) that records
  every intentional config change an agent or person makes: what changed, why, the before-state, how
  it was verified, and the exact reversal, plus a README change log anyone can scan. Turns one-off
  fixes into something a future session can audit and undo. Use when the user says "log this in my
  machine config repo", "record what you changed", "create a config repo for my handhelds like the
  Windows one", "what did we change on this PC", "how do I undo that", or after any system change
  (drivers, services, registry, startup items, mods, network settings). Ships journal.py (init / add)
  + tests.
allowed-tools: Bash, Read, Write, Edit, Grep, Glob
argument-hint: "<repo path> [init|add] [title]"
---

# machine-config-journal

Agents change machines fast and forget faster. A journal repo makes every change answerable:
"what state is this PC in, who put it there, and how do I get back?" It also stops repeat work:
the "ruled out" section of last month's entry is this month's head start.

## Shape of the repo

```
README.md              title, machine summary, change log table, analyses, runbooks, guiding rules
docs/YYYY-MM-DD-<slug>.md   one doc per session or change
tools/                 small reusable scripts that belong to this machine (optional)
```

```bash
python ${CLAUDE_SKILL_DIR}/scripts/journal.py init ~/repos/gaming-pc-config --title "Gaming PC config" --about "Streaming host, RTX GPU, Wi-Fi only"
python ${CLAUDE_SKILL_DIR}/scripts/journal.py add  ~/repos/gaming-pc-config --title "Startup trim" --summary "Edge auto-launch off; Store startup tasks off"
python ${CLAUDE_SKILL_DIR}/scripts/journal.py add  ~/repos/gaming-pc-config --kind analysis --title "Dev cleanup sweep" --summary "Almost nothing to clean; where the space is"
```

Then fill the generated doc and commit and push in the same session.

## What every entry holds

1. **Before:** command output captured before the change (versions, setting values, service start
   types). Prose like "it was set to Medium" cannot be verified later; pasted output can.
2. **What was done:** exact commands or UI steps.
3. **Verified:** what was observed afterwards and the command that shows it. Say plainly what was
   *not* verified (the symptom never reproduced, a number is a single sample).
4. **Reversal:** commands that restore the before-state. If something cannot be restored exactly
   (an unrecorded start type, a format), say so.
5. **Ruled out:** what was checked and cleared, with evidence.
6. **Follow-ups (not applied):** suggestions with the reason, so they are not mistaken for changes.
7. **Amendments after review:** when an independent review finds an overreach (a causal claim the data
   does not support, a misread diagnostic), correct it in a dated table with severity. Do not
   silently rewrite the earlier text.

## Rules

- **Private repo** by default: these docs name hardware, paths, IPs and accounts. Never put secrets in
  it (passwords, tokens, license keys, recovery codes), private or not.
- **Reversible by default:** disable rather than uninstall; park rather than delete.
- A **never-touch list** in the README (what the machine exists for: streaming host, VPN, audio,
  drivers). If a change has to touch one, amend the rule in the README with the reason, in the same
  commit, instead of quietly breaking it.
- Point-in-time numbers (free space, counts, live versions) belong in dated docs, not in the README's
  timeless sections, where they rot.
- One repo per machine or device family (a PC repo, a handhelds repo); cross-link instead of mixing.
- Commit and push at the end of every session that changed something.

## When to write an entry

After any change to drivers, services, scheduled tasks, startup items, registry, firewall, power or
network settings, game mods or launch options, emulator configs, and after any investigation worth
not repeating (write it as an analysis). Skills that change machines (`windows-host-cleanup`,
`network-stutter-triage`, `game-mod-setup`, `game-render-injection`, `handheld-ftp-backup`) should end
here.

## Origin

From two such repos, one for a Windows gaming and streaming PC and one for a set of handhelds, that
grew to dozens of dated entries. The pattern earned its keep when an independent review retracted
a latency claim (recorded as an amendment, not erased), when a later session needed the exact
reversal for a startup change, and when "ruled out" lists stopped the same Wi-Fi checks being re-run.
