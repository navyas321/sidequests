---
name: game-render-injection
description: >-
  Inject an upscaler or neural-rendering model (for example DLSS 5 through an OptiScaler fork, a
  ReShade add-on chain, or a screen-capture overlay) into a PC game that does not offer it, safely
  and reversibly: pick the route per game, check anti-cheat and the publisher's policy before
  touching anything, verify the model file's signature, place the proxy next to the real shipping
  exe, prove it runs from the injector's own log, and keep a per-game ledger of where it is on and
  how to take it off. Use when the user says "inject DLSS 5 / OptiScaler / ReShade into <game>",
  "make DLSS 5 work in this game", "will this get me banned", "it crashes with BattlEye", "is it
  actually running", "remove it but keep it restorable", or "which games have it on".
allowed-tools: Bash, PowerShell, Read, Write, Edit, Grep, Glob, WebFetch, WebSearch
argument-hint: "<game> [route A|B|C]"
---

# game-render-injection

Injection is easy to get "working" and hard to get **safely, provably and reversibly** working. The
three failures that matter: a hardware ban from an anti-cheat that treats any injected DLL as a cheat,
a model DLL from a leaked or patched build, and a mod that loads but never actually runs (0 dispatches)
while everyone admires a placebo.

Pair with `game-mod-setup` for the snapshot / park / restore ledger (`modledger.py`).

## 1. Anti-cheat and policy first (stop here if it fails)

1. Look in the game folder and services for kernel anti-cheat: BattlEye (`BEService`, `BEDaisy`),
   Easy Anti-Cheat, Ricochet-style drivers, Vanguard. Check whether the driver runs in offline or
   campaign modes too (Windows System log 7045/7036 around launch, or `Get-Service` while running).
2. Read the **publisher's own security policy**. Some name "injectors" or software that modifies
   game data "on disk or in memory" with device-level, unappealable bans, with no exception for
   visual or single-player mods. Absence of ban reports is not evidence of safety.
3. Some titles ship an official switch that starts story/offline mode without anti-cheat (a launch
   option such as `-nobattleye`). Only use a switch the publisher provides, and only for offline play.
4. Default: **stop** if the anti-cheat driver is active in the mode they will play. Offline or
   campaign play does not lower the risk when the driver runs there too. If the user still wants
   it, get explicit acceptance of the risk in their own words and write "remove before online"
   into the ledger.
5. Never disable, hide from, or tamper with an anti-cheat driver.

Observed (not documented by BattlEye): a refused in-process DLL failed to load with Windows error 1450
(STATUS_INSUFFICIENT_RESOURCES, `0xC000009A`), and one add-on in a chain loaded while the next was
refused. Do not confuse it with BattlEye's own "Blocked loading of file" message, or with the
unrelated "Failed to initialize BattlEye Service: Driver load error (1450)" at startup.

## 2. Pick the route

| Route | How | Best for | Trade-off |
| --- | --- | --- | --- |
| **A: upscaler proxy** (OptiScaler-style, `winmm.dll` / `.asi`) | Hooks the game's own DLSS/FSR/XeSS call and feeds the model real depth + motion vectors | Games that already ship an upscaler (DX12) | Best quality; needs the game's upscaler switched **on** in its settings |
| **B: ReShade + feeder add-ons** (`dxgi.dll` + add-on pair) | Estimates inputs from the frame, usually DLAA only | DX11/DX9 games with no upscaler (32-bit ones may need DXVK and a 32-bit Vulkan layer) | Lower quality; more DLLs for anti-cheat to block |
| **C: screen-capture overlay** | Captures the desktop and draws a click-through overlay; nothing is injected | Anti-cheat games, or anything A/B cannot reach | Borderless/windowed only, adds latency (tens of ms), no depth or motion data |

Read the tool's source or installer before running it: what files it writes, whether it overwrites
existing ones, whether uninstall removes only its own files, and whether it reaches outside the game
folder. Prefer young repos only after that review; avoid unsigned "one-click" installers that fetch
leaked binaries.

## 3. The model file

- Use only a copy with a **valid vendor Authenticode signature** (`Get-AuthenticodeSignature`), and
  record its version and SHA-256. A game with official support for the feature may ship a clean copy.
- A patched or unsigned model cannot pass the signature check; do not fetch community "leaked"
  copies on the user's behalf.

## 4. Install

1. Find the folder with the **real shipping exe**, not the launcher at the install root (Unreal:
   `<Game>\Binaries\Win64`; some titles have a separate campaign exe in its own folder).
2. Snapshot it (`modledger.py snapshot`), then install. Confirm afterwards that every pre-existing
   file kept its hash and only the tool's files were added.
3. Force the API the route needs: many games default to DX11 where the model will not run.
   Unreal: `-dx12` launch argument or `DefaultGraphicsRHI_DX12` in the user `Engine.ini` (back it up).
4. Skip the launcher when possible (Steam `-applaunch <id>` plus the game's own skip flags) so the
   real exe is what starts.
5. Anything registered outside the game folder (a machine-wide Vulkan layer, a registry key) goes in
   the ledger with its exact removal step.

## 5. Prove it runs

- Read the injector's log after real gameplay: **dispatch count, input and output resolution, no
  model errors**. `SR None` / 0 dispatches means the game's own upscaler is off; turn it on in game.
- Many games create no feature until a save is loaded: test in the world, not at the title screen.
- Ray Reconstruction (path tracing) usually moves the model after the upscaler; note where it ran.
- Sample GPU load, power and **VRAM headroom**; near-full VRAM explains later hitches.
- Say plainly what was **not** measured (fps cost, picture quality). Window captures only compare
  picture quality when the camera position is identical.

## 6. Ledger, parking and removal

Keep one line per game: route, files, launch options, extra registrations, the anti-cheat status and
"remove before online" if relevant, plus the removal command. To turn it off but keep it:
`modledger.py park ... --to <park dir>`; restore is hash-checked. Don't trust a store's "verify
files" to remove injected DLLs.

## Gotchas

- Hot-keys differ per tool (the overlay key may be F6, Insert or Home) and a keyboard without a
  numpad or Num Lock can hide the default; check the tool's ini before saying the menu "doesn't work".
- Visual oddities after injection (fish-eye stretch, black bars) are often the game's FOV or aspect
  handling, fixed by a game-specific tweak tool, not by the injector.
- Frame generation and the injected model can coexist; test each on its own before blaming one.
- A model swap (different weights or versions) is a change too: record it and keep the previous file.

## Origin

Built from a week of injecting a neural-rendering model into about ten PC games (Unreal, REDengine,
Creation Engine, RAGE, a DX11-only racer with BattlEye, a 32-bit DXVK title) on an RTX 50-series
card. The working rules came from what failed: a launcher that never started the real exe, 0 dispatches
until the in-game upscaler was turned on, BattlEye refusing one add-on of a chain, and model files
whose provenance could not be proven.
