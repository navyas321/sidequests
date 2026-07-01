#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coord.py -- multi-agent COORDINATION + COMMUNICATION helper for life-in-tabs.

Many Claude sessions + the headless autodev watcher work this repo in parallel. Without
coordination they clobber each other's claims, edit the same files, and race on shared
singletons (the Claude_Preview render port, the serve_life claude slot, the git index.lock).
This module is a thin, dependency-free CLI + importable library over data/coordination.json
that fixes the four observed failure modes:

  1. ACTOR-KEY COLLISION -- every interactive session used the SAME "interactive_loop" key,
     so each writer clobbered the previous session's claims/note. FIX: per-session actor keys
     "sess-<shortid>" (from CLAUDE_SESSION_ID, else a stable per-process id persisted to
     data/cache/coord-selfid). The watcher keeps its "watcher" key.
  2. NO FILE LEASES -- only backlog-ID claims existed, so two agents edited the same .html/.py
     concurrently and autodev's `git add -A` swept up others' uncommitted edits. FIX: per-actor
     file leases (files:[{path,since}]) + a check-before-edit command.
  3. NO COMMS -- each actor had a single "note" the next writer overwrote. FIX: an append-only,
     capped, TTL-pruned _bulletin.
  4. RESOURCE STARVATION -- the preview port, the serve_life claude slot, and git index.lock were
     all first-come, no fairness / no visibility. FIX: named resource leases (_resources) + a
     `git` wrapper that serializes commits behind the "git" resource lease.

DESIGN INVARIANTS (kept identical to serve_life so both sides interoperate):
  * encoding="utf-8" on every read/write.
  * Atomic writes: tmp + os.replace.
  * BACKWARD-COMPATIBLE with the BL-215 actor-section contract: existing sections keep
    {claimed:[], updatedAt|lastRun, note}; underscore-prefixed top-level keys are non-actor.
  * On EVERY load, auto-expire stale actors + their leases by heartbeat TTL (mirrors
    serve_life._COORD_HEARTBEAT_TTL + _load_coordination): interactive 20 min, watcher 7 h,
    resource default 10 min. An actor/lease is LIVE only if its heartbeat is within TTL.
  * Cross-process file lock (atomic O_CREAT|O_EXCL on data/coordination.lock, stale-lock breaking
    after >30s) around every read-modify-write, mirroring serve_life._bl_id_lock.
  * Fail-soft: a corrupt / missing coordination.json is treated as empty; never crash the caller.

Inspiration (concept only, no code copied): sidequests session-context (durable shared repo
state that survives a fresh session), usage-limit-guard (atomic writes, TTL expiry, repo-is-state),
and the lease+bulletin pattern from vibemis (concept only).
"""

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import time
import uuid

# ---------------------------------------------------------------------------
# Paths -- resolved from this file so coord.py works from any cwd (agent
# threads reset cwd between calls; we must never rely on it).
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)                                   # repo root (parent of scripts/)
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
COORD_PATH = os.path.join(DATA_DIR, "coordination.json")
COORD_LOCK = os.path.join(DATA_DIR, "coordination.lock")
SELFID_PATH = os.path.join(CACHE_DIR, "coord-selfid")

# ---------------------------------------------------------------------------
# TTLs (seconds) -- mirror serve_life._COORD_HEARTBEAT_TTL semantics.
# ---------------------------------------------------------------------------
TTL_INTERACTIVE = 20 * 60          # per-session actors ("sess-*", "interactive_loop", "interactive-opus", ...)
TTL_WATCHER = 7 * 3600             # the headless autodev "watcher"
TTL_RESOURCE_DEFAULT = 10 * 60     # a held resource lease with no explicit ttl
TTL_UNKNOWN = 3600                 # fallback for an unrecognised actor (matches serve_life default)

_ACTOR_TTL = {"watcher": TTL_WATCHER, "interactive_loop": TTL_INTERACTIVE, "interactive-opus": TTL_INTERACTIVE}

LOCK_STALE_S = 30                  # break a coordination.lock older than this (crash recovery)
LOCK_ACQUIRE_TIMEOUT_S = 10        # give up acquiring the file lock after this (degrade gracefully)
GIT_LEASE_WAIT_S = 20              # how long the git wrapper waits for the "git" resource lease
BULLETIN_CAP = 50                  # append-only bulletin ring size
BULLETIN_DEFAULT_TTL = 24 * 3600   # a bulletin entry with no explicit ttl

# non-actor top-level keys (in addition to any "_"-prefixed key)
_RESERVED_KEYS = {"_doc", "_sessions", "_resources", "_bulletin"}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def _now():
    return _dt.datetime.now()


def _now_iso():
    # naive local ISO (seconds) -- matches the existing updatedAt format in coordination.json
    return _now().replace(microsecond=0).isoformat()


import re as _re

# Matches fractional seconds with MORE than 6 digits, e.g. the watcher's ".7562233" (.NET/PowerShell
# "o"/round-trip format). Python 3.10's datetime.fromisoformat only accepts 3- or 6-digit fractions
# and raises on 7+, so we truncate to 6 before parsing. Group 1 = the extra digits to drop.
_ISO_FRAC7 = _re.compile(r"(\.\d{6})\d+")


def _parse_iso(ts_raw):
    """Parse an ISO-8601 timestamp; return None on failure. Tolerates both naive and tz-aware.

    IMPORTANT (BL-479 review fix): the watcher writes ``lastRun``/``updatedAt`` with 7-digit
    fractional seconds + a tz offset (e.g. ``2026-07-01T01:23:58.7562233-04:00``, the .NET/PowerShell
    round-trip format). Python 3.10's ``datetime.fromisoformat`` cannot parse >6 fractional digits and
    raises -- which would make ``_age_s`` return None and ``_actor_fresh`` treat the watcher as
    ETERNALLY FRESH, so its 7h TTL would NEVER fire and a crashed watcher's claims / file / resource
    leases would be held forever. Truncating the fraction to 6 digits makes it parseable so the TTL
    actually expires."""
    if not ts_raw:
        return None
    try:
        return _dt.datetime.fromisoformat(ts_raw)
    except Exception:
        pass
    try:
        return _dt.datetime.fromisoformat(_ISO_FRAC7.sub(r"\1", str(ts_raw), count=1))
    except Exception:
        return None


def _age_s(ts_raw):
    """Age in seconds of an ISO timestamp; None if unparseable/missing."""
    ts = _parse_iso(ts_raw)
    if ts is None:
        return None
    now = _dt.datetime.now(ts.tzinfo) if ts.tzinfo else _dt.datetime.now()
    return (now - ts).total_seconds()


def _actor_ttl(who):
    if who in _ACTOR_TTL:
        return _ACTOR_TTL[who]
    if who.startswith("sess-"):
        return TTL_INTERACTIVE
    return TTL_UNKNOWN


def _actor_fresh(sec, who):
    """True if actor section `sec` has a heartbeat within its TTL.
    A missing/unparseable heartbeat is treated as FRESH (don't punish an older claim format that
    predates the heartbeat field) -- mirrors serve_life._coordination_fresh."""
    ts_raw = sec.get("updatedAt") or sec.get("lastRun") or ""
    age = _age_s(ts_raw)
    if age is None:
        return True
    return age <= _actor_ttl(who)


# ---------------------------------------------------------------------------
# Self identity (per-session actor key)
# ---------------------------------------------------------------------------
def _short_from(s):
    return "".join(c for c in str(s) if c.isalnum())[:8].lower()


def whoami_key():
    """This actor's coordination key.

    Priority:
      1. env COORD_ACTOR      -- explicit override. REQUIRED for parallel sessions (each sets its own
                                 sess-<id>; the watcher passes "watcher"). This is the reliable path.
      2. env CLAUDE_SESSION_ID first 8 chars -> "sess-<shortid>".
      3. FALLBACK: a MACHINE-WIDE id persisted to data/cache/coord-selfid -> "sess-<shortid>". BL-485:
         this COLLIDES across any sessions that don't set COORD_ACTOR (Bash subprocesses rarely inherit
         CLAUDE_SESSION_ID), so it warns to stderr; it only gives correct single-session continuity.
    """
    override = (os.environ.get("COORD_ACTOR") or "").strip()
    if override:
        return override
    sid = (os.environ.get("CLAUDE_SESSION_ID") or "").strip()
    if sid:
        short = _short_from(sid)
        if short:
            return "sess-" + short
    # BL-485: the persisted id is MACHINE-WIDE -- any session without COORD_ACTOR/CLAUDE_SESSION_ID in
    # its env (the common Bash-tool-subprocess case) resolves to the SAME key and COLLIDES with other
    # sessions. Warn loudly (once) so the caller sets COORD_ACTOR=sess-<their-session>; continuity is
    # still preserved for the single-session case.
    fid = "sess-" + _self_persisted_id()
    _warn_shared_fallback(fid)
    return fid


_WARNED_FALLBACK = [False]
def _warn_shared_fallback(fid):
    """BL-485: one loud stderr warning when the shared machine-wide fallback actor is used."""
    if _WARNED_FALLBACK[0]:
        return
    _WARNED_FALLBACK[0] = True
    try:
        import sys as _sys
        _sys.stderr.write(
            "coord.py WARNING: no COORD_ACTOR / CLAUDE_SESSION_ID in env -- using the SHARED machine-wide "
            "fallback actor '" + fid + "'. Other sessions without COORD_ACTOR COLLIDE on this key. "
            "Set COORD_ACTOR=sess-<your-session-shortid> on every coord.py call.\n")
    except Exception:
        pass


def _self_persisted_id():
    """Read (or create) a stable 8-char id in data/cache/coord-selfid. Fail-soft: on any IO error
    fall back to an ephemeral per-process id derived from uuid (still valid, just not persisted)."""
    try:
        with open(SELFID_PATH, "r", encoding="utf-8") as f:
            v = _short_from(f.read().strip())
            if v:
                return v
    except Exception:
        pass
    new = _short_from(uuid.uuid4().hex)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = SELFID_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
        os.replace(tmp, SELFID_PATH)
    except Exception:
        pass
    return new


# ---------------------------------------------------------------------------
# Cross-process file lock (mirror of serve_life._bl_id_lock)
# ---------------------------------------------------------------------------
class _FileLock:
    """Context manager: atomic O_CREAT|O_EXCL lock on data/coordination.lock. Breaks a stale lock
    older than LOCK_STALE_S. After LOCK_ACQUIRE_TIMEOUT_S it proceeds UNLOCKED (graceful
    degradation -- better than deadlocking a whole fleet on one crashed writer)."""

    def __init__(self, timeout=LOCK_ACQUIRE_TIMEOUT_S):
        self.timeout = timeout
        self._fd = None

    def __enter__(self):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
        except Exception:
            pass
        deadline = time.time() + self.timeout
        while True:
            try:
                self._fd = os.open(COORD_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                try:
                    os.write(self._fd, ("%d\n" % os.getpid()).encode("ascii", "ignore"))
                except Exception:
                    pass
                break
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(COORD_LOCK) > LOCK_STALE_S:
                        os.unlink(COORD_LOCK)
                        continue
                except Exception:
                    pass
                if time.time() > deadline:
                    break  # proceed unlocked
                time.sleep(0.05)
            except Exception:
                break
        return self

    def __exit__(self, *exc):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            try:
                os.unlink(COORD_LOCK)
            except Exception:
                pass
        return False


# ---------------------------------------------------------------------------
# Load / save (with auto-expiry on every load)
# ---------------------------------------------------------------------------
def _read_raw():
    try:
        with open(COORD_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def _prune(coord):
    """Auto-expire stale actors + leases. Returns (coord, changed).

      * Stale actor (heartbeat past TTL): clear its claimed[] and files[] and append an
        auto-expire marker to its note -- mirrors serve_life BL-167 behaviour (the actor key is
        kept so its identity/history persists; only its holds are released).
      * _resources: drop any resource whose holder is not a LIVE actor OR whose own since+ttl expired.
      * _bulletin: drop entries whose at+ttl expired; cap to the newest BULLETIN_CAP.
    """
    changed = False

    # Which actors are currently live? (used to expire resource leases held by dead actors)
    live_actors = set()
    for who, sec in coord.items():
        if who in _RESERVED_KEYS or who.startswith("_") or not isinstance(sec, dict):
            continue
        if _actor_fresh(sec, who):
            live_actors.add(who)

    # 1. Expire stale actor holds.
    for who, sec in coord.items():
        if who in _RESERVED_KEYS or who.startswith("_") or not isinstance(sec, dict):
            continue
        if _actor_fresh(sec, who):
            continue
        if sec.get("claimed") or sec.get("files"):
            sec["claimed"] = []
            sec["files"] = []
            note = (sec.get("note") or "").strip()
            marker = "[coord: auto-expired stale heartbeat]"
            if marker not in note:
                sec["note"] = (note + " " + marker).strip()
            changed = True

    # 2. Expire resource leases.
    res = coord.get("_resources")
    if isinstance(res, dict):
        for name, lease in list(res.items()):
            if not isinstance(lease, dict):
                res.pop(name, None); changed = True; continue
            holder = lease.get("holder")
            ttl = lease.get("ttl") or TTL_RESOURCE_DEFAULT
            age = _age_s(lease.get("since"))
            dead_holder = holder is not None and holder not in live_actors
            expired = age is not None and age > ttl
            if dead_holder or expired:
                res.pop(name, None)
                changed = True
        if not res:
            # keep the key present (as {}) only if it already existed; harmless either way
            coord["_resources"] = res

    # 3. Prune bulletin.
    bul = coord.get("_bulletin")
    if isinstance(bul, list):
        kept = []
        for e in bul:
            if not isinstance(e, dict):
                changed = True; continue
            ttl = e.get("ttl") or BULLETIN_DEFAULT_TTL
            age = _age_s(e.get("at"))
            if age is not None and age > ttl:
                changed = True; continue
            kept.append(e)
        if len(kept) > BULLETIN_CAP:
            kept = kept[-BULLETIN_CAP:]
            changed = True
        if len(kept) != len(bul):
            changed = True
        coord["_bulletin"] = kept

    return coord, changed


def load():
    """Load coordination.json, applying auto-expiry (in-memory). Does NOT write. Fail-soft: returns
    {} on a missing/corrupt file. For a load that persists expiry, use load_and_persist()."""
    coord, _ = _prune(_read_raw())
    return coord


def _write_raw(coord):
    """Atomic write (tmp + os.replace), utf-8, indent=2, ensure_ascii=False (matches serve_life)."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = COORD_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(coord, f, indent=2, ensure_ascii=False)
        os.replace(tmp, COORD_PATH)
        return True
    except Exception:
        return False


def load_and_persist():
    """Load + auto-expire + persist if anything expired. Runs under the file lock so it can't race
    another writer. Returns the pruned coord."""
    with _FileLock():
        coord, changed = _prune(_read_raw())
        if changed:
            _write_raw(coord)
        return coord


def save(coord):
    """Atomic persist of a full coord dict (no lock -- callers that mutate should use _mutate())."""
    return _write_raw(coord)


def _mutate(fn):
    """Run fn(coord) -> (coord, result) as an atomic read-modify-write under the file lock, applying
    auto-expiry first so every write also cleans stale holds. Returns fn's result."""
    with _FileLock():
        coord, _ = _prune(_read_raw())
        coord, result = fn(coord)
        _write_raw(coord)
        return result


def _actor_section(coord, actor):
    sec = coord.get(actor)
    if not isinstance(sec, dict):
        sec = {"claimed": [], "note": ""}
        coord[actor] = sec
    sec.setdefault("claimed", [])
    return sec


def _is_watcher(actor):
    return actor == "watcher"


def _touch_heartbeat(sec, actor):
    """Set the heartbeat field appropriate to the actor kind (watcher uses lastRun; others updatedAt).
    Keeps both if both already exist (watcher section historically carries both)."""
    ts = _now_iso()
    if _is_watcher(actor):
        sec["lastRun"] = ts
    sec["updatedAt"] = ts


# ---------------------------------------------------------------------------
# Live-holder queries (used by check-file / conflict reporting)
# ---------------------------------------------------------------------------
def _norm_path(p):
    """Normalise a path for lease comparison: make relative-to-ROOT if under ROOT, forward slashes,
    lowercase drive letter. Absolute paths outside ROOT are kept as-is (normcase)."""
    if not p:
        return p
    raw = p.strip().strip('"').strip("'")
    try:
        ap = os.path.abspath(raw)
        rel = os.path.relpath(ap, ROOT)
        if not rel.startswith(".."):
            return rel.replace("\\", "/")
        return os.path.normcase(ap).replace("\\", "/")
    except Exception:
        return raw.replace("\\", "/")


def file_holder(coord, path, exclude=None):
    """Return the actor key of a LIVE actor holding a lease on `path` (other than `exclude`), or None."""
    target = _norm_path(path)
    for who, sec in coord.items():
        if who in _RESERVED_KEYS or who.startswith("_") or not isinstance(sec, dict):
            continue
        if who == exclude:
            continue
        if not _actor_fresh(sec, who):
            continue
        for f in (sec.get("files") or []):
            if isinstance(f, dict) and _norm_path(f.get("path")) == target:
                return who
    return None


def resource_holder(coord, name):
    """Return (holder, lease) for a LIVE-held resource `name`, else (None, None). Prune already ran,
    so anything still in _resources is held by a live actor and unexpired -- but re-check defensively."""
    res = coord.get("_resources")
    if not isinstance(res, dict):
        return None, None
    lease = res.get(name)
    if not isinstance(lease, dict):
        return None, None
    holder = lease.get("holder")
    # defensive: holder must still be a live actor
    sec = coord.get(holder)
    if isinstance(sec, dict) and _actor_fresh(sec, holder):
        return holder, lease
    # holder actor missing but lease unexpired by its own ttl -> still honour it
    age = _age_s(lease.get("since"))
    ttl = lease.get("ttl") or TTL_RESOURCE_DEFAULT
    if age is not None and age <= ttl:
        return holder, lease
    return None, None


# ---------------------------------------------------------------------------
# Public library API
# ---------------------------------------------------------------------------
def heartbeat(note=None, actor=None):
    """Refresh this actor's heartbeat (and optionally its note). Creates the actor section if new."""
    actor = actor or whoami_key()

    def fn(coord):
        sec = _actor_section(coord, actor)
        if note is not None:
            sec["note"] = note
        _touch_heartbeat(sec, actor)
        return coord, dict(sec)

    return _mutate(fn)


def acquire_file(paths, actor=None):
    """Acquire file lease(s). All-or-nothing: if ANY path is held by another live actor, acquire
    NONE and return {"ok": False, "conflicts": {path: holder}}. On success returns
    {"ok": True, "held": [paths]} and refreshes the heartbeat."""
    if isinstance(paths, str):
        paths = [paths]
    actor = actor or whoami_key()
    norm = [_norm_path(p) for p in paths]

    def fn(coord):
        conflicts = {}
        for p in norm:
            h = file_holder(coord, p, exclude=actor)
            if h:
                conflicts[p] = h
        if conflicts:
            return coord, {"ok": False, "conflicts": conflicts}
        sec = _actor_section(coord, actor)
        files = sec.get("files") or []
        have = {_norm_path(f.get("path")) for f in files if isinstance(f, dict)}
        for p in norm:
            if p not in have:
                files.append({"path": p, "since": _now_iso()})
        sec["files"] = files
        _touch_heartbeat(sec, actor)
        return coord, {"ok": True, "held": [f["path"] for f in files]}

    return _mutate(fn)


def release_file(paths, actor=None):
    """Release specific file lease(s) held by this actor. Returns {"ok": True, "remaining": [...]}."""
    if isinstance(paths, str):
        paths = [paths]
    actor = actor or whoami_key()
    norm = {_norm_path(p) for p in paths}

    def fn(coord):
        sec = coord.get(actor)
        if not isinstance(sec, dict):
            return coord, {"ok": True, "remaining": []}
        files = [f for f in (sec.get("files") or [])
                 if isinstance(f, dict) and _norm_path(f.get("path")) not in norm]
        sec["files"] = files
        _touch_heartbeat(sec, actor)
        return coord, {"ok": True, "remaining": [f["path"] for f in files]}

    return _mutate(fn)


def release_all(actor=None):
    """Release ALL file leases AND resource leases held by this actor. Use at session end."""
    actor = actor or whoami_key()

    def fn(coord):
        released_files, released_res = [], []
        sec = coord.get(actor)
        if isinstance(sec, dict):
            released_files = [f.get("path") for f in (sec.get("files") or []) if isinstance(f, dict)]
            sec["files"] = []
            _touch_heartbeat(sec, actor)
        res = coord.get("_resources")
        if isinstance(res, dict):
            for name, lease in list(res.items()):
                if isinstance(lease, dict) and lease.get("holder") == actor:
                    res.pop(name, None)
                    released_res.append(name)
        return coord, {"ok": True, "files": released_files, "resources": released_res}

    return _mutate(fn)


def check_file(paths):
    """Return {path: holder-or-None} for each path (holder = a LIVE actor other than self)."""
    if isinstance(paths, str):
        paths = [paths]
    me = whoami_key()
    coord = load()
    return {p: file_holder(coord, p, exclude=me) for p in paths}


def acquire_resource(name, ttl=None, actor=None):
    """Acquire the named resource lease. If a LIVE actor already holds it, acquire nothing and return
    {"ok": False, "holder": who, "since": ...}. On success {"ok": True}."""
    actor = actor or whoami_key()

    def fn(coord):
        holder, lease = resource_holder(coord, name)
        if holder and holder != actor:
            return coord, {"ok": False, "holder": holder, "since": (lease or {}).get("since")}
        res = coord.get("_resources")
        if not isinstance(res, dict):
            res = {}
            coord["_resources"] = res
        res[name] = {"holder": actor, "since": _now_iso(), "ttl": int(ttl) if ttl else TTL_RESOURCE_DEFAULT}
        _touch_heartbeat(_actor_section(coord, actor), actor)
        return coord, {"ok": True, "holder": actor, "resource": name}

    return _mutate(fn)


def release_resource(name, actor=None):
    """Release the named resource lease if this actor holds it. Returns {"ok": True}."""
    actor = actor or whoami_key()

    def fn(coord):
        res = coord.get("_resources")
        if isinstance(res, dict):
            lease = res.get(name)
            if isinstance(lease, dict) and lease.get("holder") in (actor, None):
                res.pop(name, None)
        return coord, {"ok": True, "resource": name}

    return _mutate(fn)


def announce(text, kind="info", ttl=None, actor=None):
    """Append an entry to the append-only _bulletin (capped, TTL-pruned). kind in {info,warn,act}."""
    actor = actor or whoami_key()
    if kind not in ("info", "warn", "act"):
        kind = "info"
    entry = {"at": _now_iso(), "from": actor, "kind": kind,
             "text": str(text)[:500], "ttl": int(ttl) if ttl else BULLETIN_DEFAULT_TTL}

    def fn(coord):
        bul = coord.get("_bulletin")
        if not isinstance(bul, list):
            bul = []
        bul.append(entry)
        if len(bul) > BULLETIN_CAP:
            bul = bul[-BULLETIN_CAP:]
        coord["_bulletin"] = bul
        _touch_heartbeat(_actor_section(coord, actor), actor)
        return coord, dict(entry)

    return _mutate(fn)


def bulletin(since=None):
    """Return bulletin entries (optionally only those with at > since ISO), newest last."""
    coord = load_and_persist()
    entries = coord.get("_bulletin")
    if not isinstance(entries, list):
        return []
    if since:
        cut = _parse_iso(since)
        if cut is not None:
            out = []
            for e in entries:
                ts = _parse_iso(e.get("at"))
                if ts is None or ts > cut:
                    out.append(e)
            return out
    return list(entries)


def status():
    """Situational-awareness snapshot: live actors (+ their claims/files/note/age), held resources,
    recent bulletin. Persists auto-expiry as a side effect."""
    coord = load_and_persist()
    me = whoami_key()
    actors = []
    for who, sec in coord.items():
        if who in _RESERVED_KEYS or who.startswith("_") or not isinstance(sec, dict):
            continue
        if not _actor_fresh(sec, who):
            continue
        ts_raw = sec.get("updatedAt") or sec.get("lastRun") or ""
        age = _age_s(ts_raw)
        actors.append({
            "actor": who,
            "me": who == me,
            "claimed": list(sec.get("claimed") or []),
            "files": [f.get("path") for f in (sec.get("files") or []) if isinstance(f, dict)],
            "note": (sec.get("note") or "")[:280],
            "heartbeat": ts_raw,
            "age_s": int(age) if age is not None else None,
        })
    actors.sort(key=lambda a: (not a["me"], a["actor"]))
    resources = {}
    res = coord.get("_resources")
    if isinstance(res, dict):
        for name, lease in res.items():
            if isinstance(lease, dict):
                resources[name] = {"holder": lease.get("holder"), "since": lease.get("since"),
                                   "ttl": lease.get("ttl")}
    bul = coord.get("_bulletin")
    recent = [e for e in (bul if isinstance(bul, list) else [])][-10:]
    return {"me": me, "actors": actors, "resources": resources, "bulletin": recent}


# ---------------------------------------------------------------------------
# git wrapper -- serialize commits behind the "git" resource lease
# ---------------------------------------------------------------------------
def run_git(gitargs, wait=GIT_LEASE_WAIT_S):
    """Acquire the "git" resource lease (poll up to `wait`s with small backoff), run `git <gitargs>`
    in ROOT, release the lease. Serializes commit/index.lock races across the fleet. Returns
    {"ok", "returncode", "stdout", "stderr", "waited_s"}. If the lease can't be won in time we run
    anyway (git's own index.lock is the last-resort guard) but flag it."""
    actor = whoami_key()
    deadline = time.time() + wait
    delay = 0.1
    got = False
    while True:
        r = acquire_resource("git", ttl=120, actor=actor)
        if r.get("ok"):
            got = True
            break
        if time.time() >= deadline:
            break
        time.sleep(delay)
        delay = min(delay * 1.5, 1.0)
    waited = round(wait - max(0.0, deadline - time.time()), 2)
    try:
        proc = subprocess.run(["git", "-C", ROOT] + list(gitargs), cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
        return {"ok": proc.returncode == 0, "returncode": proc.returncode,
                "stdout": proc.stdout, "stderr": proc.stderr,
                "lease": "held" if got else "degraded-no-lease", "waited_s": waited}
    except Exception as e:
        return {"ok": False, "returncode": -1, "stdout": "", "stderr": str(e),
                "lease": "held" if got else "degraded-no-lease", "waited_s": waited}
    finally:
        if got:
            release_resource("git", actor=actor)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _pj(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _fmt_age(sec):
    if sec is None:
        return "?"
    if sec < 90:
        return "%ds" % int(sec)
    if sec < 5400:
        return "%dm" % int(sec / 60)
    return "%.1fh" % (sec / 3600.0)


def _cmd_whoami(a):
    print(whoami_key())
    return 0


def _cmd_heartbeat(a):
    sec = heartbeat(note=a.note)
    _pj({"ok": True, "actor": whoami_key(), "updatedAt": sec.get("updatedAt"), "note": sec.get("note")})
    return 0


def _cmd_claim_file(a):
    r = acquire_file(a.paths)
    if not r.get("ok"):
        for p, holder in r["conflicts"].items():
            print("CONFLICT: %s is leased by LIVE actor %s" % (p, holder))
        _pj(r)
        return 2
    _pj(r)
    return 0


def _cmd_release_file(a):
    _pj(release_file(a.paths))
    return 0


def _cmd_release_all(a):
    _pj(release_all())
    return 0


def _cmd_check_file(a):
    held = check_file(a.paths)
    conflict = False
    for p, holder in held.items():
        if holder:
            conflict = True
            print("HELD: %s -> LIVE actor %s" % (p, holder))
        else:
            print("free: %s" % p)
    _pj(held)
    return 2 if conflict else 0


def _cmd_acquire(a):
    r = acquire_resource(a.name, ttl=a.ttl)
    if not r.get("ok"):
        print("BUSY: resource '%s' held by LIVE actor %s (since %s)" % (a.name, r.get("holder"), r.get("since")))
        _pj(r)
        return 2
    _pj(r)
    return 0


def _cmd_release(a):
    _pj(release_resource(a.name))
    return 0


def _cmd_git(a):
    if not a.gitargs:
        print("usage: coord.py git -- <git args...>")
        return 2
    r = run_git(a.gitargs)
    if r.get("stdout"):
        sys.stdout.write(r["stdout"])
        if not r["stdout"].endswith("\n"):
            sys.stdout.write("\n")
    if r.get("stderr"):
        sys.stderr.write(r["stderr"])
    print("[coord.git] lease=%s waited=%ss rc=%s" % (r.get("lease"), r.get("waited_s"), r.get("returncode")))
    return 0 if r.get("ok") else (r.get("returncode") or 1)


def _cmd_announce(a):
    _pj(announce(a.text, kind=a.kind, ttl=a.ttl))
    return 0


def _cmd_bulletin(a):
    entries = bulletin(since=a.since)
    if not entries:
        print("(bulletin empty)")
        return 0
    for e in entries:
        print("%s [%s] %s: %s" % (e.get("at"), (e.get("kind") or "info").upper(), e.get("from"), e.get("text")))
    return 0


def _cmd_status(a):
    snap = status()
    if a.json:
        _pj(snap)
        return 0
    print("== coord status ==  (me: %s)" % snap["me"])
    print("-- live actors (%d) --" % len(snap["actors"]))
    if not snap["actors"]:
        print("  (none live)")
    for act in snap["actors"]:
        tag = " *ME*" if act["me"] else ""
        print("  %-16s hb=%-4s%s" % (act["actor"], _fmt_age(act["age_s"]), tag))
        if act["claimed"]:
            print("      claimed: %s" % ", ".join(act["claimed"]))
        if act["files"]:
            print("      files:   %s" % ", ".join(act["files"]))
        if act["note"]:
            print("      note:    %s" % act["note"])
    print("-- held resources (%d) --" % len(snap["resources"]))
    if not snap["resources"]:
        print("  (none)")
    for name, lease in snap["resources"].items():
        print("  %-16s holder=%s since=%s" % (name, lease.get("holder"), lease.get("since")))
    print("-- recent bulletin (%d) --" % len(snap["bulletin"]))
    if not snap["bulletin"]:
        print("  (empty)")
    for e in snap["bulletin"]:
        print("  %s [%s] %s: %s" % (e.get("at"), (e.get("kind") or "info").upper(), e.get("from"), e.get("text")))
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="coord.py",
        description="Multi-agent coordination + communication helper over data/coordination.json.")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("whoami", help="print this actor's coordination key").set_defaults(func=_cmd_whoami)

    hb = sub.add_parser("heartbeat", help="refresh this actor's heartbeat (+ optional note)")
    hb.add_argument("--note", default=None)
    hb.set_defaults(func=_cmd_heartbeat)

    cf = sub.add_parser("claim-file", help="acquire file lease(s); exit 2 on conflict")
    cf.add_argument("paths", nargs="+")
    cf.set_defaults(func=_cmd_claim_file)

    rf = sub.add_parser("release-file", help="release specific file lease(s)")
    rf.add_argument("paths", nargs="+")
    rf.set_defaults(func=_cmd_release_file)

    sub.add_parser("release-all", help="release all file + resource leases held by this actor").set_defaults(func=_cmd_release_all)

    chk = sub.add_parser("check-file", help="show any LIVE holder of each path; exit 2 if held by another")
    chk.add_argument("paths", nargs="+")
    chk.set_defaults(func=_cmd_check_file)

    ac = sub.add_parser("acquire", help="acquire a resource lease; exit 2 if a live actor holds it")
    ac.add_argument("name")
    ac.add_argument("--ttl", type=int, default=None, help="lease TTL seconds (default 600)")
    ac.set_defaults(func=_cmd_acquire)

    rl = sub.add_parser("release", help="release a resource lease")
    rl.add_argument("name")
    rl.set_defaults(func=_cmd_release)

    g = sub.add_parser("git", help="run git behind the 'git' resource lease (serializes commits)")
    g.add_argument("gitargs", nargs=argparse.REMAINDER,
                   help="git args after a literal --, e.g.  coord.py git -- status --short")
    g.set_defaults(func=_cmd_git)

    an = sub.add_parser("announce", help="append a message to the bulletin")
    an.add_argument("text")
    an.add_argument("--kind", default="info", choices=["info", "warn", "act"])
    an.add_argument("--ttl", type=int, default=None)
    an.set_defaults(func=_cmd_announce)

    bl = sub.add_parser("bulletin", help="print recent bulletin entries")
    bl.add_argument("--since", default=None, help="ISO timestamp; only entries after it")
    bl.set_defaults(func=_cmd_bulletin)

    st = sub.add_parser("status", help="situational-awareness snapshot")
    st.add_argument("--json", action="store_true", help="emit JSON instead of the human table")
    st.set_defaults(func=_cmd_status)

    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 0
    # The git subparser's REMAINDER captures a leading "--"; strip it so callers can write
    #   coord.py git -- status --short
    if args.cmd == "git" and args.gitargs and args.gitargs[0] == "--":
        args.gitargs = args.gitargs[1:]
    try:
        return args.func(args)
    except SystemExit:
        raise
    except Exception as e:
        # Fail-soft: never crash the caller with a traceback.
        _pj({"ok": False, "error": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
