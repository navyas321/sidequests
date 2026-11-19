---
name: settings-ab-test
description: >-
  Answer "which setting is better?" and "why does it flicker/stutter?" for games, streaming apps and
  drivers with evidence instead of guesses: pin the exact installed version, read that version's own
  docs or source before naming any option, then run a small controlled A/B test (alternating runs,
  one variable, each run one sample), capture frame timing with PresentMon and the app's own logs,
  and judge it with an exact permutation test that says plainly when a difference is not proven.
  Use when the user says "stop guessing", "research and back it up with data", "balanced or low
  latency?", "is X better than Y", "why does the screen flicker", "verify my hypothesis", "what
  settings performed best in my logs", or "give me concrete answers". Ships abtest.py (+ tests).
allowed-tools: Bash, PowerShell, Read, Write, Grep, Glob, WebFetch, WebSearch
argument-hint: "<app> <setting> <value A> <value B>"
---

# settings-ab-test

Settings questions invite confident guesses: an option name from a different version, a "lower
latency" claim nobody measured, a flicker blamed on the first plausible cause. Users notice, and the
trust cost is high. This skill is the discipline: verify the option exists, measure, and report
what the data can and cannot say.

## 1. Before answering anything

1. **Pin the version.** Read the installed version from the app (About page, file version, log
   header). Builds differ: an experimental build may add or rename the very option in question.
2. **Read that version's documentation, changelog or source,** and cite it (page, file and line).
   Do not name a setting you have not seen in docs or on the user's screen. If you cannot see the UI,
   ask for a screenshot of the settings page rather than describing an option that may not exist.
3. Label every claim as **verified** (seen in docs, code, logs or measurements) or **inferred**.
4. When the user offers a hypothesis ("I think it was G-Sync"), test it against the data before
   agreeing, and say what would disprove it. Their next observation may overturn it: a flicker blamed
   on variable refresh turned out to be the app's frame-pacing mode interacting with it.

## 2. Look at the logs you already have

Before a new test, mine existing logs: the app's session logs, the driver or injector logs, the
streaming host's logs. Line up timestamps of setting changes with events (drops, reconnects, decode
spikes, model dispatch failures) and aggregate per setting: count, rate per minute, worst stretch.
This often answers the question, or at least narrows it to one variable.

## 3. Design a small fair test

- **One variable.** Everything else fixed: content/scene, resolution, fps cap, frame generation,
  refresh mode (fixed vs variable), network.
- **Alternate** A, B, A, B, so drift (heat, background load, network) spreads across both.
- **Each run is one sample.** Thousands of frames inside one run are not independent; 4 runs per
  setting is the minimum, and the smallest p-value 4 v 4 can ever show is 2/70, about 0.029. Keep the
  groups equal where you can; the script prints the smallest p the actual design can reach.
- Label files with the setting as its own word in the name (`03-balanced.csv`, `04-nogsync.csv`);
  the script matches whole words and lists any file it skipped.
- Same duration per run (30 to 60 s of steady play), started the same way.
- Keep a run log (start time, setting) and name capture files with the setting (`03-balanced.csv`).
- Let the user drive the game; you drive the capture and the bookkeeping, and confirm each run landed.

## 4. Capture

PresentMon (from its official release page) records every frame's present and display timing:
the display-change interval is what the eye sees, and frames that were never shown are marked
(a `Dropped` column in the older format, `NA` display times in the newer one). `abtest.py` reads
both formats. Always pass `--app`, since a capture can hold several processes. Run PresentMon only
for the capture, and leave nothing running or set to autostart afterwards.

With V-Sync on (no tearing) on a fixed-refresh display, frame times arrive in multiples of the
refresh interval (4.17 ms at 240 Hz). Check the distribution: at 60 fps every frame should be held 4 refreshes; a 3/5 alternation
is uneven pacing even when the average fps looks perfect.

## 5. Judge it

```bash
python ${CLAUDE_SKILL_DIR}/scripts/abtest.py presentmon <capture dir> --modes balanced,lowlat --app <game or client exe>
python ${CLAUDE_SKILL_DIR}/scripts/abtest.py runs runs.csv          # if you computed per-run metrics yourself
```

Per metric: mean per setting, difference, exact two-sided permutation p-value, and a rough count of
runs per setting needed to confirm the observed difference. Report it straight:

- p < 0.05 with a meaningful size: a real difference.
- Otherwise: "no proven difference; leans toward A by N; about K runs each would settle it".
- Name what the capture **cannot** see. For a streaming client, PresentMon's timings start inside
  the client app, so the time from a frame arriving over the network to the client presenting it
  (decode, frame generation, pacing waits) needs another method: packet capture aligned with
  present times, or a high-speed camera filming input and screen. (Newer PresentMon builds add
  input-to-photon and PC-latency columns for local games; check which your build reports.)

## 6. Recommend

If asked to pick one, pick one, give the two or three data points behind it, and say when you would
switch (for example, a fast competitive game at high fps). Keep the recommendation consistent with
the vendor's own guidance, or explain why it differs.

## 7. Clean up

Stop captures, confirm no trace session, scheduled task or startup entry was left behind, keep or
delete recordings as the user prefers, and record the result in the machine's config journal.

## Origin

From a late-night session tuning a PlayStation remote-play client on a Windows PC: three rounds of
"stop making stuff up" over options that did not exist in the installed build, a flicker first
blamed on G-Sync and then traced to the frame-pacing mode, and finally an 8-run alternating test
(about 23,000 frames) that showed the two pacing modes indistinguishable, with Balanced leaning
smoother, and exposed uneven frame-generation pacing in both.
