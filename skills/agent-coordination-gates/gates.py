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

Enforced (mirrors the production backlog API this skill was extracted from):
  create  -> a tracked item exists (title + type/priority)   [enforce in your create path, not here]
  pickup  -> status inprogress requires a named owner
  pause   -> leaving inprogress (open/paused/blocked) requires owner + progress note + validation
  close   -> any terminal status requires resolution (>=40) + a verification keyword; and a DISPOSAL
             close (wontfix/duplicate/deferred/canceled/accepted -- dropping work) ALSO requires an
             ADVERSARIAL review token ('adversarial' + the verdict). 'duplicate' is NOT exempt.
  review  -> OPTIONAL but recommended: pass `reviewer=` and the write path runs an INDEPENDENT reviewer on
             every agent terminal close and stamps a server-owned `reviewedBy`. A typed 'adversarial'
             token is self-declared -- the author can write it without any review happening -- so it is
             only the fallback when no reviewer is wired.
  human   -> HUMAN_ONLY_STATUSES (default: 'accepted') reject agent writes; the human on the board closes
             without the reviewer. Decide "is this the human?" with is_human_ua(), never with a bare
             "User-Agent starts with Mozilla" test (Windows PowerShell's default UA starts with Mozilla).
"""
import re
import datetime

UPDATE_STATUSES = {"triage", "inbox", "open", "inprogress", "accepted", "done",
                   "deferred", "wontfix", "duplicate", "paused", "blocked"}
TERMINAL_STATUSES = {"done", "shipped", "wontfix", "duplicate", "deferred", "canceled", "cancelled", "accepted"}
# A DISPOSAL close is a terminal status that DROPS the item WITHOUT delivering the work: wontfix,
# duplicate, deferred, canceled/cancelled, accepted. Dropping work is the easy way to make an item
# quietly "disappear", and a WRONG drop silently loses scope -- e.g. mislabeling something a duplicate
# buries the unique part of it. So every disposal close ALSO requires an ADVERSARIAL review token: proof
# that an INDEPENDENT check challenged whether dropping is actually correct ("is it GENUINELY a duplicate
# / already covered / truly blocked / a risk worth accepting -- did you exhaust it?"). This mirrors the
# production backlog API and is a HARD rule: 'duplicate' is NOT exempt (that omission let a real
# dup-close slip through with no review). Delivery closes (done/shipped) prove themselves via the verify
# gate instead; they are deliberately NOT in this set so routine shipping is not blocked.
DISPOSAL_STATUSES = {"wontfix", "duplicate", "deferred", "canceled", "cancelled", "accepted"}
ADVERSARIAL_RE = re.compile(r"adversar", re.I)
# States only the human may set. 'accepted' ("risk accepted") is a judgment about the user's own risk
# appetite; an agent that can write it will park inconvenient work there. Agents close with done/wontfix/
# duplicate instead, which keep their review requirements.
HUMAN_ONLY_STATUSES = {"accepted"}
REVIEW_STAMP = "independent-review"

# ---- who is calling? -----------------------------------------------------------------------------------
# Lower-case substrings that mark a SCRIPTED client even when its User-Agent starts with "Mozilla".
# Windows PowerShell 5.1 Invoke-RestMethod sends "Mozilla/5.0 (Windows NT; ...) WindowsPowerShell/5.1",
# so a gate that books "starts with Mozilla" as the human lets every agent on Windows skip the reviewer.
AGENT_UA_TOKENS = (
    "powershell",       # WindowsPowerShell/5.1 and PowerShell/7.x
    "headlesschrome",   # CDP / Puppeteer / Playwright headless runs
    "curl/", "wget/", "httpie", "python", "go-http-client", "node-fetch", "undici", "axios/",
    "okhttp", "java/", "libwww-perl",
)


def is_human_ua(ua):
    """True only for a real browser: the UA starts with 'Mozilla' AND carries no scripted-client token.
    Known limit: a User-Agent is self-declared, so a script that sends a full browser UA still passes.
    This stops HONEST scripted clients from being booked as the human, not a deliberate impersonation --
    pair it with a real auth boundary if impersonation matters."""
    s = str(ua or "").strip().lower()
    if not s.startswith("mozilla"):
        return False
    return not any(tok in s for tok in AGENT_UA_TOKENS)
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


def apply_update(item, patch, by="api", reviewer=None, actor_is_human=False):
    """Validate + apply a task-status patch through the coordination gates. Mutates `item` in place.
    Returns (True, None) on success or (False, "reason") if a gate rejects it. `patch` may carry
    status/owner/resolution/verification/progress. `by` is the acting agent id (for the audit comment).

    reviewer(item, new_status, evidence) -> (approved: bool, reason: str) is called for every AGENT
    terminal close when given. It must run in a context the author does not control (a fresh model call
    spawned by the server, a second vendor's CLI, a human queue). If it RAISES (unavailable), a `done`
    close proceeds with an auditFlag, while a DISPOSAL close fails closed -- an unreviewed drop is exactly
    the lazy-close class this gate exists to stop. actor_is_human=True (decide it with is_human_ua) skips
    the reviewer and unlocks HUMAN_ONLY_STATUSES."""
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

    if new in HUMAN_ONLY_STATUSES and not actor_is_human:
        return False, ("'%s' is a HUMAN-ONLY status: only the person on the board may set it. Close with "
                       "done / wontfix / duplicate (and their review requirements) instead." % new)
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
        # DISPOSAL closes (dropping work without delivering it -- incl. 'duplicate') ALSO need an
        # ADVERSARIAL review token: an independent challenge that dropping is genuinely correct.
        if not actor_is_human and reviewer is not None:
            try:
                approved, why = reviewer(item, new, combined)
            except Exception as e:      # reviewer unavailable
                if new in DISPOSAL_STATUSES:
                    return False, ("the independent reviewer is unavailable (%s); a DISPOSAL close fails "
                                   "closed -- retry later or route it to a human." % e)
                item["auditFlag"] = "closed without review: reviewer unavailable (%s)" % e
            else:
                if not approved:
                    return False, "independent reviewer rejected the close: %s" % why
                item["reviewedBy"] = REVIEW_STAMP
        elif not actor_is_human and new in DISPOSAL_STATUSES and not ADVERSARIAL_RE.search(combined):
            return False, ("closing to the DISPOSAL status '%s' (dropping the item without delivering it) "
                           "requires an ADVERSARIAL review: an INDEPENDENT check must have challenged 'is "
                           "dropping this correct -- is it GENUINELY a duplicate / already covered / truly "
                           "blocked / a risk worth accepting -- did you exhaust it?'. State it was "
                           "'adversarial'-reviewed and the verdict in 'resolution'/'verification'." % new)
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
        # DISPOSAL close: a duplicate that is NOT adversarially reviewed is REJECTED even though it has a
        # resolution + verification -- dropping work needs an independent challenge.
        ("dup no review",   {"status": "duplicate", "resolution": "Same as T-2 so closing this as a duplicate of it; both cover the same area.", "verification": "checked T-2"}),
        ("dup ok",          {"status": "duplicate", "resolution": "Duplicate of T-2 (same root cause). adversarial-reviewed: an independent pass confirmed no unique scope is lost here.", "verification": "checked T-2 covers it"}),
        ("agent accepted",  {"status": "accepted", "resolution": "Risk accepted: the edge case is rare and costly to fix right now.", "verification": "checked logs"}),
    ]:
        ok, err = apply_update(dict(it), patch, by="agent-a")
        print("%-16s -> %s" % (label, "OK" if ok else "REJECTED: " + err))

    # A wired reviewer replaces the self-declared token: it runs, it decides, it stamps reviewedBy.
    good = {"status": "done", "resolution": "Implemented feature X and wired it into the request handler.",
            "verification": "smoke 12/0"}
    item = dict(it)
    ok, err = apply_update(item, good, by="agent-a", reviewer=lambda i, s, e: (True, "evidence checks out"))
    print("%-16s -> %s" % ("reviewed done", ("OK reviewedBy=%s" % item.get("reviewedBy")) if ok else "REJECTED: " + err))
    ok, err = apply_update(dict(it), good, by="agent-a", reviewer=lambda i, s, e: (False, "no commit cited"))
    print("%-16s -> %s" % ("review rejects", "OK" if ok else "REJECTED: " + err))

    def _down(i, s, e):
        raise RuntimeError("reviewer offline")
    drop = {"status": "wontfix", "resolution": "Not worth doing: the page it fixes was deleted last week.",
            "verification": "checked the route returns 404"}
    ok, err = apply_update(dict(it), drop, by="agent-a", reviewer=_down)
    print("%-16s -> %s" % ("wontfix, no rev", "OK" if ok else "REJECTED: " + err))

    # Who is the human? PowerShell's default UA starts with Mozilla and must NOT pass.
    for ua in ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
               "Mozilla/5.0 (Windows NT; Windows NT 10.0; en-US) WindowsPowerShell/5.1.26100",
               "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome/131.0.0.0 Safari/537.36",
               "python-requests/2.32"):
        print("%-16s -> %-5s %s" % ("human?", is_human_ua(ua), ua[:60]))
