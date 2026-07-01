#!/usr/bin/env python
"""gates.py - the four agent-work-lifecycle GATES, framework-agnostic.

Drop this behind your ONE task-mutation write path (an HTTP endpoint, an MCP tool, or a library call) so a
fleet of autonomous agents can share one backlog without double-picks, silent drops, unverified closes, or
lost-context pauses. The gates reject any transition that lacks the metadata other agents need to coordinate.

It is storage-agnostic: `apply_update(item, patch, by=...)` takes the CURRENT item dict + the requested patch,
validates + mutates the dict in place, appends the audit comment, and returns (ok, error). YOU load the item
and persist it (two lines around the call). Pure stdlib.

    ok, err = apply_update(item, {"status": "inprogress", "owner": "opus-7e27"})
    if not ok: return http_400(err)
    save(item)                                  # your storage

Enforced (mirrors the life-in-tabs backlog API that this skill generalizes):
  create  -> a tracked item exists (title + type/priority)   [enforce in your create path, not here]
  pickup  -> status inprogress requires a named owner
  pause   -> leaving inprogress (open/paused/blocked) requires owner + progress note + validation
  close   -> any terminal status requires resolution (>=40) + a verification keyword
"""
import re
import datetime

UPDATE_STATUSES = {"triage", "inbox", "open", "inprogress", "accepted", "done",
                   "deferred", "wontfix", "duplicate", "paused", "blocked"}
TERMINAL_STATUSES = {"done", "shipped", "wontfix", "duplicate", "deferred", "canceled", "cancelled", "accepted"}
PICKUP_STATUSES = {"inprogress"}
PAUSE_STATUSES = {"paused", "blocked"}
STATUS_ALIASES = {"in_progress": "inprogress", "in-progress": "inprogress", "wip": "inprogress",
                  "doing": "inprogress", "active": "inprogress", "started": "inprogress", "claimed": "inprogress"}
RESOLUTION_MIN = 40
OWNER_MIN = 2
# The point of the verify gate: force the caller to state HOW it was confirmed, not just "done".
VERIFY_RE = re.compile(r"(verif|test|smoke|curl|render|confirm|checked|repro|passed|observ|HTTP\s*\d|/api/|/healthz)", re.I)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _comment(item, by, text):
    if not isinstance(item.get("comments"), list):
        item["comments"] = []
    item["comments"].append({"at": _now(), "by": (str(by or "api"))[:40], "text": text[:2000]})


def apply_update(item, patch, by="api"):
    """Validate + apply a task-status patch through the coordination gates. Mutates `item` in place.
    Returns (True, None) on success or (False, "reason") if a gate rejects it. `patch` may carry
    status/owner/resolution/verification/progress. `by` is the acting agent id (for the audit comment)."""
    if not isinstance(item, dict) or not isinstance(patch, dict):
        return False, "item and patch must be dicts"
    if "status" not in patch:
        # non-status edits (owner reassign, priority, detail) pass straight through
        for k in ("owner", "priority", "type", "detail", "title"):
            if k in patch:
                item[k] = patch[k]
        return True, None

    new = STATUS_ALIASES.get(str(patch["status"]).strip().lower(), str(patch["status"]).strip().lower())
    if new not in UPDATE_STATUSES:
        return False, "invalid status '%s'" % new
    old = str(item.get("status") or "").lower()
    owner = (str(patch.get("owner") or item.get("owner") or "")).strip()
    resolution = (str(patch.get("resolution") or patch.get("progress") or "")).strip()
    verification = (str(patch.get("verification") or "")).strip()
    combined = (resolution + " " + verification).strip()

    is_pause = (new not in TERMINAL_STATUSES and new not in PICKUP_STATUSES
                and (new in PAUSE_STATUSES or (old == "inprogress" and new in ("open", "triage", "inbox"))))

    # --- PICKUP gate ---
    if new in PICKUP_STATUSES:
        if len(owner) < OWNER_MIN:
            return False, ("picking up (status '%s') requires an 'owner' (>=%d chars) so agents don't "
                           "double-pick." % (new, OWNER_MIN))
    # --- CLOSE gate ---
    elif new in TERMINAL_STATUSES:
        if len(resolution) < RESOLUTION_MIN:
            return False, ("closing to '%s' requires a 'resolution' (>=%d chars) stating WHY + the STEPS "
                           "taken." % (new, RESOLUTION_MIN))
        if not VERIFY_RE.search(combined):
            return False, ("closing to '%s' requires stating HOW it was VERIFIED (a test/command/observation, "
                           "e.g. 'smoke 287/0', 'curl /healthz 200') in 'resolution' or 'verification'." % new)
    # --- PAUSE gate ---
    elif is_pause:
        if len(owner) < OWNER_MIN:
            return False, "pausing (status '%s') requires an 'owner' (who is pausing it)." % new
        if len(resolution) < RESOLUTION_MIN:
            return False, ("pausing (status '%s') requires a progress note (>=%d chars) stating PROGRESS SO "
                           "FAR + WHY paused, so the next agent can resume." % (new, RESOLUTION_MIN))
        if not VERIFY_RE.search(combined):
            return False, ("pausing (status '%s') requires stating HOW you VALIDATED the current state "
                           "(e.g. 'committed WIP, smoke still green') in 'resolution' or 'verification'." % new)

    # --- apply + audit-comment ---
    item["status"] = new
    if owner:
        item["owner"] = owner[:64]
    if new in PICKUP_STATUSES:
        _comment(item, by or owner, "Picked up by %s." % owner)
    elif new in TERMINAL_STATUSES:
        item["resolution"] = (resolution + ("\nVerified: " + verification if verification else "")).strip()
        _comment(item, by, "Closed as %s. %s" % (new, item["resolution"]))
    elif is_pause:
        note = (resolution + ("\nValidated: " + verification if verification else "")).strip()
        _comment(item, by or owner, "Paused (%s). %s" % (new, note))
    else:
        _comment(item, by, "Status: %s -> %s" % (old or "open", new))
    return True, None


if __name__ == "__main__":
    # tiny self-demo: each rejection prints its coordinating reason, then the valid form succeeds.
    it = {"id": "T-1", "status": "open", "title": "demo"}
    for label, patch in [
        ("pickup no owner", {"status": "inprogress"}),
        ("pickup ok",       {"status": "inprogress", "owner": "agent-a"}),
        ("close no res",    {"status": "done"}),
        ("close no verify", {"status": "done", "resolution": "did the thing because it seemed fine to close"}),
        ("close ok",        {"status": "done", "resolution": "Implemented feature X and wired it into the request handler.", "verification": "smoke 12/0"}),
    ]:
        ok, err = apply_update(dict(it) if "pickup" in label else it, patch, by="agent-a")
        print("%-16s -> %s" % (label, "OK" if ok else "REJECTED: " + err))
