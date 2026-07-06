---
name: hdr-gaming-setup
description: >-
  Set up and VERIFY the full Windows 11 HDR gaming pipeline on an OLED/HDR
  monitor with an NVIDIA RTX GPU: monitor OSD, Windows HDR Calibration (HGIG
  first-clip method), NVIDIA RTX HDR + Dynamic Vibrance, and a log-proven
  in-game engagement test. Use when you hear: "set up HDR", "calibrate my
  OLED/HDR monitor", "RTX HDR settings", "Dynamic Vibrance values", "HDR looks
  washed out / too bright / wrong", "is RTX HDR actually on?", "verify HDR is
  working", or "what nits do I enter in the Windows HDR Calibration app".
  Evidence-first: every claim is probed on the machine, never trusted from a
  spec sheet or a previous session.
allowed-tools: Bash, Read, Write
argument-hint: "[probe|setup|verify]"
---

# hdr-gaming-setup

A verification-first playbook for the four-layer Windows HDR gaming stack:

1. **Monitor hardware** (OSD picture mode, peak brightness, energy savers)
2. **Windows** (HDR toggle, HDR Calibration app profile, SDR content brightness)
3. **NVIDIA driver** (RTX HDR + RTX Dynamic Vibrance per-game)
4. **The game** (native HDR vs driver HDR, display/window mode, config file)

The core rule: **probe, set, then prove engagement from driver logs** — do not
declare success because a toggle looks on. Each layer can silently defeat the
others (Auto HDR overrides, profile mis-association, games rewriting their own
config on exit).

---

## Flow 1 — Probe ground truth (`probe`)

Run all probes BEFORE changing anything; rerun after to diff. All stdlib
Python + shell; no third-party tools. `${CLAUDE_SKILL_DIR}/scripts/hdr_probe.py`
bundles them — run it and read the JSON.

What it collects and why it matters:

| Probe | Source | What it answers |
|---|---|---|
| Raw EDID parse | `HKLM\SYSTEM\CurrentControlSet\Enum\DISPLAY\*\*\Device Parameters\EDID` | The panel's own declared HDR peak (MaxTML), MaxFALL, min luminance from the CTA-861 HDR static-metadata block. This is the number calibration should track — not the marketing "1300 nits" |
| Active displays + HDR state | `QueryDisplayConfig` + `DisplayConfigGetDeviceInfo(GET_ADVANCED_COLOR_INFO)` | Which displays are live, refresh rate, whether HDR (advanced color) is ON, bit depth, SDR white level |
| Active HDR color profile | `mscms!ColorProfileGetDisplayDefault(scope, adapterLuid, sourceId, CPT_ICC, CPST_EXTENDED_DISPLAY_COLOR_MODE=8, ...)` | THE authoritative answer for which calibration profile is live on a display. **Do not infer this from ICM registry slot numbers** — `ProfileAssociations\Display\{GUID}\NNNN` keys do not reliably track today's `Enum\DISPLAY\...\Driver` values (instance numbers get reused across reconnects); registry-slot inference produces false positives |
| Auto HDR overrides | `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` | Per-app `AutoHDREnable=...` entries override the global toggle. A per-app Auto HDR override on a game will fight RTX HDR even when global Auto HDR is off |
| NVIDIA driver version | `nvidia-smi --query-gpu=driver_version --format=csv,noheader` | RTX HDR multi-monitor needs >= 565.90 (Oct 2024, NVIDIA official) |
| Game config file | varies per game (check PCGamingWiki "Configuration file location") | Native HDR flag, window mode, target display. Beware sibling games by the same publisher with similar config paths — verify you have THE game's file |

## Flow 2 — Set the recommended stack (`setup`)

### Monitor OSD (research the exact model first — cite manual + reviews)
- Pick the calibration-capable **game/Gamer picture mode**, not Vivid.
- **Peak brightness: High** (or the mode that raises the EDID-declared MaxTML).
- **Disable any "smart energy saving"** luminance-compensation feature — it
  silently dims the panel and invalidates calibration.
- Keep OLED-care features ON (pixel orbit, screen saver); they don't affect
  picture accuracy.
- OSD brightness at max for HDR (Windows expects the display at reference).
- Note: vendor desktop apps (DDC/CI) usually expose picture mode/brightness but
  NOT deep OSD items (peak-brightness tier, energy savers) — those need the
  physical joystick once.

### Windows HDR Calibration app (HGIG method)
- Calibrate **in the final gaming picture mode / peak setting** — MHC profiles
  record "the display state at the time of measurement" (Microsoft). Change the
  OSD later => recalibrate.
- All three patterns use the same stop rule: **slider until the gray squares
  just disappear** (first clipping point). On OLED, min luminance lands at 0.
- Sanity-check the results against the EDID: max ≈ MaxTML, full-frame ≈
  MaxFALL. If someone entered spec-sheet numbers instead of doing the visual
  pass, the profile may still be right on honest panels (OLEDs clip rather than
  tone-map) — but only eyes confirm.
- Saturation slider: leave near default; the wide-gamut panel + driver features
  already add punch.
- SDR content brightness afterwards: ~120-210 nits desktop white is the
  comfortable range (slider ≈ (nits − 80) / 4.2). Lower = less OLED wear.
- The profile is display-specific; verify with the `ColorProfileGetDisplayDefault`
  probe, and re-verify after sleep/input-switch events (Windows has a known
  multi-monitor bug that cross-applies profiles).

### NVIDIA App — per-game driver settings
- **RTX HDR: On** (per-game or global). Requirements: Windows HDR ON, game's
  native HDR OFF, Auto HDR OFF (global AND per-app), works on DX9/11/12/Vulkan.
- Hard conflicts to keep off: **Fast Sync, DSR/DLDSR, NVIDIA Image Scaling,
  Surround/Clone mode**.
- **RTX Dynamic Vibrance: On**, Intensity 50 / Saturation boost 50 (community
  consensus; drop intensity to 25-30 if dark scenes look lifted). Stacks fine
  with RTX HDR. Note it persists via the NVIDIA App daemon per-launch, not as a
  DRS blob — that's normal.
- RTX HDR tunables live in the in-game overlay (Alt+Z > Game Filter) on current
  App builds, not the App page. Recommended values for an SDR-mastered game on
  an OLED:
  - **Peak brightness = the calibrated/EDID peak** (the App inherits Windows
    HDR Calibration values automatically — fix calibration first).
  - **Middle greys = paperWhite x 0.5^gamma** → 44 for 200-nit paper white at
    gamma 2.2 (match your Windows SDR white level for desktop/game coherence).
  - **Contrast +25** (default 0 decodes ~gamma 2.0; +25 ≈ 2.2).
  - **Saturation −50** = neutral; RTX HDR's 0 already over-saturates, and
    Vibrance should be the single punch knob. Taste range: −50..−20.
  - Overlay sliders apply **across all profiles** (global) — flag that.

### The game
- If reviewers/HDR databases classify the game's native HDR as "SDR in an HDR
  container" (common in JRPG ports), turn native HDR OFF and use RTX HDR.
- Games rewrite their config on exit — **re-read the config file after the
  user has been in the menus** to confirm your edits survived. Prefer making
  display-mode changes in the game's own menu.
- Exclusive fullscreen is the safe mode for RTX HDR multi-monitor setups
  (borderless has documented dropout reports; borderless needs the App's
  "Optimizations for windowed games" toggle).

## Flow 3 — Prove engagement (`verify`)

Toggles lie; the driver's own log doesn't. The NVIDIA App backend daemon logs
every RTX HDR / Vibrance application with the target PID:

```
%LOCALAPPDATA%\NVIDIA Corporation\NVIDIA App\NvBackend\backend.log
```

1. Record the log's byte size. Launch the game (Steam: `start steam://rungameid/<appid>`).
2. Read from the recorded offset and look for lines matching your game's exe
   and the launch PID:
   - `AIHDR::SetAIHDRState_V2 ... processId=<pid> enabled=1 peakBrightness=...`
   - `NvAPI_SYS_SetTrueHDRParams() set realtime AIHDR successfully` ← RTX HDR engaged
   - `AIDVC::setFeatureStateForApp ... enabled=1 intensity=... saturation=...`
   - `NvAPI_Set_DeepDVC_Intensity() succeeded` ← Vibrance engaged
   - `QueryTrueHDRSupport_V2 ... maxPeakBrightness: <n>` should equal your
     calibrated peak.
3. Re-run the display probe DURING gameplay: HDR still on, right display.
4. Eyes pass (the only non-automatable step): correct exposure, no washout,
   shadows intact. If the machine's user is present, have them confirm; a
   screenshot sanity-check catches gross failures only (HDR is tone-mapped in
   captures).
5. Never kill the game process to "clean up" without checking for an active
   session — verify it's at a title screen first, or leave it running.

## Failure modes seen in the wild (check these first)

- Per-app `AutoHDREnable` override fighting RTX HDR while global Auto HDR is off.
- Calibration profile associated/checked via registry slots → false alarm or
  wrong-display association; only `ColorProfileGetDisplayDefault` is truth.
- Config edit made on disk, then silently reverted by the game on exit.
- Similar-named config of a sibling game inspected by mistake.
- Marketing peak (e.g. "1300 nits") entered in calibration instead of the
  EDID/measured value — panel clips far lower in real modes.
- "Smart energy saving" OSD feature quietly dimming a calibrated panel.
