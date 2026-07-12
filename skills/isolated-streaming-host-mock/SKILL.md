---
name: isolated-streaming-host-mock
description: >-
  Stand up an ISOLATED mock game-streaming host (Sunshine / Apollo / Vibepollo) on a
  machine that ALREADY runs a real one, so you can pair and stream a test client against it
  WITHOUT disrupting real gaming or the real host's pairings. Use when you need a throwaway
  second streaming host for a test client, when "my second host collides with the real
  Sunshine/Apollo ports", when a bare external config crashes the second instance
  ("terminate called recursively" / "Platform failed to initialize"), or when a mock host
  keeps grabbing the physical monitor. Windows; the copied-prefix + port-offset + kill-by-port
  technique generalizes to any Sunshine-lineage host.
allowed-tools: Bash, Read, Write, PowerShell
argument-hint: "[setup|start|stop|verify]"
---

# Isolated mock streaming host (Sunshine/Apollo/Vibepollo)

You want to test a Moonlight-family **client** against a real streaming **host**, but the only
host you have is the one you actually game on. Pointing tests at it risks clobbering its
pairings, its config/state, and — worst — grabbing the physical display mid-game. The fix is a
**second, fully isolated instance of the same host** that shares nothing with the real one.

Naively running the host binary a second time does **not** work — these hosts (Sunshine and its
forks Apollo / Vibepollo) assume a single install:

- **Same binary, same default ports.** A second process binds the real host's defaults
  (47984 / 47989 / 47990 / 48010) and collides.
- **Shared config/state dir.** A second process reads/writes the real pairings and state DB —
  and the running real service *locks* some of those files (you'll see `error=5` ACL/DB write
  failures in the log).
- **A bare external config crashes.** Launching the binary against a lone `sunshine.conf`
  outside its install prefix fails to find its assets/shaders and dies with
  `Error: Platform failed to initialize` → `terminate called recursively`.
- **It can grab your monitor.** By default the host can capture the primary display — a mock
  that does that will interrupt whatever you're playing.

This skill isolates all four: a **copied install prefix**, **offset ports**, **run-from-its-own-dir**,
and a **virtual-display / no-capture** posture — plus a **kill-by-port-only** stop that can never
take down the real host (same binary name).

## When to use

- You're developing or testing a streaming client and need a real host to pair/stream against,
  but the machine's only host is the one you game on and must not be disturbed.
- A second host instance collides on ports, corrupts the real pairings, or crashes on launch.
- A test/mock host keeps taking over the physical screen.
- You want a disposable, reproducible host you can start before a test cycle and kill after,
  leaving the real host byte-for-byte untouched.

## The four isolation techniques (all four are required)

| Technique | What it prevents |
|---|---|
| **Copy the full install prefix** to an isolated dir | The launch crash — the binary needs its own `assets/` (shaders), `plugins/`, `tools/`, `config/`, `state`. |
| **Offset ports** via `port = <base>` in the copied config | Port collision with the real host's 47984/47989/47990/48010. |
| **Run from its own directory** (cwd = prefix) with its own config | Reading/writing the real host's config & state; shader/asset resolution failures. |
| **Never capture the physical display** (virtual display only) | Interrupting your game — the mock must never grab the monitor. |

## Flow A — build the isolated prefix (one-time setup)

Copy the **entire** real install prefix into a scratch dir, excluding only the volatile
per-install bits (logs, saved state, and creds/pairings — you want a *clean* mock, and the
running real service locks some of these anyway). The rest — `assets/`, `plugins/`, `tools/`,
`drivers/`, the binary and its DLLs — must be present or the mock crashes on launch.

```powershell
$real = "C:\Program Files\Apollo"          # the REAL host's install prefix (example)
$mock = "C:\path\to\mock-host\host"        # your isolated copy (NOT under Program Files)

# Copy the whole prefix, then drop the volatile/locked bits so the mock starts clean.
robocopy $real $mock /E /XD logs config\logs config\covers config\session_history `
  /XF *.log sunshine_state.json vibeshine_state.json session_history credentials
# (Locked files the real SERVICE holds — a few logs/state/certs — will simply be skipped;
#  they are non-essential to a fresh mock. Copy errors on those are expected and fine.)
```

Then drop a **clean minimal config** at `$mock\config\sunshine.conf` (see
`${CLAUDE_SKILL_DIR}/scripts/mock.conf`) — just the offset `port` and a distinct
`sunshine_name`. The copied prefix supplies everything else. The mock now has its own
`assets/config/state` and never reads or writes the real `C:\Program Files\Apollo`.

> Why the full copy: a lone config outside the prefix can't resolve `assets/shaders/...`, so the
> host logs `Cannot create vertex shader ... bytecode is missing` → `Platform failed to
> initialize` and then `terminate called recursively`. Copying the prefix fixes it because the
> binary finds its assets relative to its own working directory (Flow C).

## Flow B — offset the ports

In the copied `config\sunshine.conf`, set a **base port** far from the real host's defaults:

```
port = 48900
sunshine_name = Example-Mock-Host
```

**Every port the host opens derives from `port`** (web UI = base+1, HTTPS = base-5,
RTSP = base+21, the UDP media ports = base+9..+13, …). So a single `port = 48900` moves the
*whole* set out of the real host's way (which sits on the 47984/47989/47990/48010 cluster). Pick
any base with a clear gap; 48900 is a convenient example.

## Flow C — run it from its own directory (isolated state)

Launch the copied binary with **cwd set to the prefix** and point it at the *relative* config
path, so assets resolve and all state stays inside the copy:

```powershell
scripts\start-mock.ps1 -Dir "C:\path\to\mock-host\host" -BasePort 48900
```

`start-mock.ps1` is idempotent (no-op if the base port is already bound), runs the binary hidden
with `-WorkingDirectory <prefix>`, waits, then confirms **its own PID** owns the base port and
prints the connect addresses. Running from the prefix (not a bare config) is what avoids the
crash in Flow A.

> **Extra isolation for a *shared* config:** if you ever run the binary against a config that the
> real host also uses, add the host's `-1` flag ("do not load or save persistent state") so the
> run neither reads nor mutates saved pairings/state. For a fully copied prefix (this skill) you
> don't need it — the state dir is already private — but it's the belt-and-suspenders option.

## Flow D — never take over the screen

A mock must be invisible to your gaming:

- **Idle = no capture.** Left alone, the host captures nothing; the physical monitor is untouched.
- **Stream via a virtual display.** When a client connects, use a **virtual-display driver**
  (e.g. **SudoVDA**, which ships with Apollo/Vibepollo) so the stream renders to a *virtual*
  monitor — the physical one you game on is never grabbed.
- **Do NOT set `dd_configuration_option = ensure_primary`** in a mock — that forces it onto the
  primary physical display. Leave display config at its default.

Note the GPU/encoder is still shared even when the display isn't — run stream tests when you
aren't actively gaming so you don't contend for the encoder.

## Flow E — connect from the test client

- **Bind `0.0.0.0`** (the host default) so a client elsewhere on the LAN/tailnet can reach it —
  not just loopback.
- **Stream host address:** `<host-ip>:<base>` — the client's "Add PC" / manual-IP connects to
  the **base** port (e.g. `<host-ip>:48900`). Over Tailscale use the host's **tailnet IP**
  (the `100.x.y.z` CGNAT address) or its MagicDNS name.
- **mDNS discovery:** the client can also find it by `sunshine_name` (e.g. `Example-Mock-Host`).
- **Web manager (PIN pairing / settings):** `https://<host-ip>:<base+1>` — log in with the creds
  from your config.

## Flow F — safe stop (kill by port, NEVER by name)

The real host runs the **same binary name** (`sunshine.exe`), so a `Stop-Process -Name` or
`pkill sunshine` would kill the real host too. Stop **only** the PID that owns the mock's base
port:

```powershell
scripts\stop-mock.ps1 -BasePort 48900 -RealPort 47989
```

`stop-mock.ps1` finds the base-port owner and kills exactly that PID. **Guard:** if that PID is
somehow also the owner of the real host's port, it **aborts** rather than risk the real service.
Never match by process name anywhere in the stop path.

## Flow G — validate the isolation

Prove the mock is up *and* the real host is untouched:

```powershell
# 1) The mock answers as itself (hostname + unpaired status). Moonlight-family serverinfo:
#    a plain HTTP GET to the base port returns <hostname> and <PairStatus>0</PairStatus>.
Invoke-WebRequest "http://<host-ip>:48900/serverinfo?uuid=0" -UseBasicParsing | Select -Expand Content
#    expect: <hostname>Example-Mock-Host</hostname> ... <PairStatus>0</PairStatus>

# 2) The real host's ports are STILL owned by the REAL pid, before AND after starting the mock.
Get-NetTCPConnection -State Listen | ? LocalPort -in 47984,47989,47990,48010 |
  Select LocalPort, OwningProcess
#    the OwningProcess for these must be unchanged by start-mock / stop-mock.
```

The mock returning its own `sunshine_name` with `PairStatus 0` (unpaired) confirms it's a clean,
separate instance; the real host's ports keeping the same owner PID across start/stop confirms
non-disruption.

## Reference scripts (in `scripts/`)

- **`start-mock.ps1`** — idempotent start; copies-prefix assumptions baked into the comments;
  runs from the prefix with offset base port; prints connect addresses.
- **`stop-mock.ps1`** — kills only the base-port owner; refuses if it's the real host's PID.
- **`mock.conf`** — the minimal `port = <base>` + `sunshine_name` config to drop in the copied
  prefix's `config/`.

Parameterize `-Dir`, `-BasePort`, `-RealPort` for your machine.

## Notes & limits

- **Nothing here is a secret** — the only per-machine values are your isolated dir path, the base
  port you pick, the host's LAN/tailnet IP, and the web-manager creds you set. Keep those out of
  anything you commit.
- The mock is **disposable**: delete the copied prefix to remove it entirely; it never touched the
  real install.
- Works for **any Sunshine-lineage host** (Sunshine, Apollo, Vibepollo) because they share the
  port-derivation model, the single-install assumption, and the `sunshine.conf` format. The
  default real-host ports (47984/47989/47990/48010) are the Sunshine defaults; adjust
  `-RealPort` if your real host uses a custom base.
