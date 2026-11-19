---
name: network-stutter-triage
description: >-
  Find out why game or video streaming stutters on a home network, on Windows hosts and handheld
  clients, without breaking the link you are standing on. Baseline first, then one interleaved ping
  loop across the gateway, other clients and the suspect device to decide "the network or that one
  device", read the adapter's real capabilities (spatial streams, USB port speed, link vs throughput),
  change one thing at a time with a recorded before-state and a revert, and source drivers only from
  trusted catalogs. Use when the user says "my stream stutters", "is it my Wi-Fi or the device",
  "I get 300 Mbps but my plan is 1 Gbps", "should I buy a Wi-Fi adapter", "streaming broke on the new
  network", "you made it worse, revert", or "it worked yesterday". Ships interleaved_ping.ps1 +
  ping_report.py (+ tests).
allowed-tools: Bash, PowerShell, Read, Write, Grep, Glob, WebFetch, WebSearch
argument-hint: "<suspect device> [gateway] [other clients]"
---

# network-stutter-triage

Network "fixes" are where agents most often make things worse: a registry tweak plus an adapter
restart gets credited with an improvement the restart alone caused, a driver from a forum replaces a
working one, and the only network path to the machine goes down mid-change. Measure first, change
one thing, keep the way back.

## 1. Baseline before touching anything

Record, and commit as an artifact rather than prose:

- Gateway and a known-good wired/wireless client: loss, avg, p95, max (60+ pings each).
- NIC error and discard counters, with uptime (`Get-NetAdapterStatistics`). These reset when the
  adapter restarts, so only the pre-change reading means anything.
- Wireless event log for link drops and roam storms (`Microsoft-Windows-WLAN-AutoConfig/Operational`).
- Adapter facts: model, driver version and date, spatial streams, band, link rate, power plan and
  the adapter's power-saving mode.

If loss and errors are zero and the link is stable, frame it as **contention or jitter**, not a fault.
On recent Windows 11 builds (24H2 and later), `netsh wlan show interfaces` (RSSI, channel, rate)
needs Location services on: ask before turning it on just for a diagnostic.

## 2. Network or that one device: interleave

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/interleaved_ping.ps1" -Targets 192.168.1.1,192.168.1.20,192.168.1.30 -Seconds 150 -Out pings.csv
python "${CLAUDE_SKILL_DIR}/scripts/ping_report.py" pings.csv --suspect 192.168.1.30
```

One loop pings every target back to back, so each row measures all of them at nearly the same moment
(a lost ping delays the later targets in that pass by up to the timeout). If the suspect shows
repeated high samples that **never coincide** with high samples on the gateway or other clients, the
router, the host radio and shared airtime are exonerated in one run. The report refuses to clear the
network on one or two isolated spikes. Separate per-target runs cannot
support that claim, and parallel runs make the targets compete.

- Run nothing else from that host while recording; a concurrent scan once made a 5 ms gateway read 90 ms.
- **Plateaus** (pinned high for seconds, then back) mean the radio is away or buffering (power save,
  background scans, roaming). Isolated spikes mean something else. Report the shape, not just the max.
- Reproduce the symptom while recording (start a stream). A clean run with no stream proves little.

## 3. Throughput questions (adapter purchase, "I only get 300 Mbps")

- Compare the PC with a phone in the same spot on the same speed test before blaming the PC.
- Link rate is not throughput. A 1x1 radio tops out around half of a 2x2 one; antennas are not always
  streams, so read the spatial-stream count from the driver or a WLAN report.
- A USB adapter on a **USB 2.0 port** is capped near 300 Mbps whatever it is rated for. Check the port's
  negotiated speed before concluding anything about the adapter.
- When adding an adapter, disable the radio it replaces and confirm which one carries the default route.
- Ethernet beats every Wi-Fi tweak for a streaming host. If the port is unplugged, say so first.

## 4. Changing things safely

1. **One change at a time,** each with its before-value written down and a one-line revert.
2. **Never credit a change when the procedure also restarted the adapter.** A restart clears a doze
   state and zeroes counters by itself. Do a control: revert, re-measure with the same sample size.
3. Stationary desktop: roaming aggressiveness at the lowest setting is a reasonable precaution, not a
   proven fix. Driver updates can rename the registry keyword and silently reset it, so re-check
   advanced properties after any driver change.
4. **Drivers:** Windows Update, the OEM, or the Microsoft Update Catalog only, never forum or
   aggregator builds. Prove the package matches the device's exact hardware/subsystem ID before
   installing, export the current driver first, and if that NIC is the only network path, install
   detached with automatic link check and rollback.
5. **Orphans:** vendor network services for hardware that is no longer fitted (a phantom device,
   `Present: False`) can be disabled, reversibly.
6. **"You made it worse":** revert immediately and confirm the revert, then investigate. Do not stack
   a second fix on a first one that hurt.

## 5. "It worked yesterday"

Diff what changed since then before theorising: driver installs (`pnputil /enum-drivers`, SetupAPI
log), Windows updates, new or changed firewall rules, services whose start type changed, and which
network profile is active. On a **new network**, Windows may mark it Public while the streaming host's
inbound rules only cover Private; compare `Get-NetConnectionProfile` with the rules' profiles.

## 6. Wedges that look like a network fault

- A streaming host whose sends stop on one particular NIC, or a game process that has exited but cannot
  be killed (threads stuck in a kernel wait, sockets still open), points at the NIC driver's send path,
  not at the app. In one observed case (a USB Wi-Fi adapter on a game-streaming host), stopping the
  Quality Windows Audio Video Experience service (qWave) made the wedge go away; it is worth a test,
  not a known fix, and the setting did not survive later updates, so re-check it after reboots.
- After any interrupted or rejected call that started an elevated or detached process, read its log
  and re-check the state before saying what did or did not happen: the child keeps running.

## Ruled-out list

End every investigation with "checked and cleared, do not chase again" (loss, roam storms, drive read
speed, power saving, orphan processes), with the evidence, so the next session starts further ahead.

## Origin

From several stutter investigations on a home network with a Windows game-streaming host and a
Linux handheld client: a 150-second interleaved run cleared the whole mesh router in one go, a
"16 ms to 3 ms" win was retracted after review because an adapter restart explained all of it, a USB
adapter's speed hinged on the port, and a host wedge on one NIC tracked a QoS service.
