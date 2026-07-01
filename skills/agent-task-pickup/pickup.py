"""Agent task-pickup ranking — WSJF-Lite band-first scorer + Autonomy Gate.

A project-agnostic, pure-stdlib reference implementation for deciding WHICH task an autonomous agent
(or a fleet of them draining a shared backlog) should pick up next. Two orthogonal mechanisms the
naive "sort by priority" conflates:

  ORDER       = a numeric score decides ranking, but severity is a HARD BAND, not just a weighted term.
  ELIGIBILITY = a separate gate ROUTES (never silently drops) work an autonomous agent shouldn't
                self-assign (security / severe / architecture / underspecified / file-conflicting) to a
                human/senior lane.

Feed it a list of plain dicts (your backlog items) and get back {items, gated}. Adapt the field names,
weights, and gate rules to your system — the STRUCTURE is the reusable part. See SKILL.md for the
design rationale and the adversarial-review lessons baked in here.

    from pickup import rank
    out = rank(items, actor="watcher", leased_paths={"serve_life.py": "other-agent"})
    top = out["items"][0]          # highest-ranked auto-pickable task (has ["score"] and ["why"])
    out["gated"]                   # [{... , "gatedReason": "..."}] routed to a human/senior lane

Item dict fields consulted (all optional; every term degrades to a NEUTRAL value, never a penalty):
  id, priority (critical|high|medium|low), type, title, detail, source, created (ISO), effort (S|M|L|XL),
  epic|parent, children[], status.
"""
import re
import datetime as _dt

# --- Ordering: severity BAND is a hard primary key (critical strictly outranks high). ----------------
PRIO_BAND  = {"critical": 0, "high": 1, "medium": 2, "low": 3}          # lower = ranked first
PRIO_SCORE = {"critical": 1.0, "high": 0.65, "medium": 0.4, "low": 0.15}  # intra-band value term only

# --- Cost-of-Delay: how fast value decays if delayed (by type + a security-keyword nudge). -----------
TYPE_CRIT  = {"security": 1.0, "bug": 0.7, "spike": 0.5, "task": 0.4, "automation": 0.4,
              "page": 0.25, "feature": 0.3, "enhancement": 0.3, "story": 0.25, "epic": 0.1}
# --- Job-size (WSJF denominator): effort if known, else inferred from type, plus per-child weight. ---
TYPE_SIZE  = {"bug": 1.5, "task": 1.5, "automation": 1.5, "security": 1.5, "page": 2,
              "spike": 2, "feature": 3, "enhancement": 3, "story": 3, "epic": 8}
EFFORT_SIZE = {"S": 1, "M": 2, "L": 3, "XL": 5}

SEC_RE = re.compile(r"(security|auth|csrf|token|permission|bypass|leak|pii|privacy|cve|xss|injection|"
                    r"secret|credential)", re.I)
# EXACT user-provenance allowlist. NOT startswith('user') — that lets an agent spoof 'userspace-x' /
# 'user_agent' into the top tier. Only strings a trusted capture path actually writes earn 1.0.
USER_RE = re.compile(r"^user(-request|-directive|-live-review|-live|-\d{4}-\d{2}-\d{2})?$", re.I)

REVIEW_ELIGIBLE = frozenset({"open", "triage", "accepted"})   # reach scoring even if "parked"
GATE_TYPES      = frozenset({"epic", "spike", "security"})
GATED_ACTORS    = frozenset({"watcher", "autodev"})           # these get the gate; others bypass

# Numerator weights (Cost-of-Delay). Tune to taste; they only reorder WITHIN a severity band.
W_SEVERITY, W_TIMECRIT, W_PROVENANCE, W_ENABLEMENT = 0.34, 0.24, 0.20, 0.12
AGING_CAP, AGING_PER_DAY = 0.12, 0.008   # bounded anti-starvation nudge (saturates ~15 days)


def _age_days(ts, now):
    """Whole days since an ISO timestamp; 0 (never negative, never raises) if missing/unparseable."""
    if not ts:
        return 0
    try:
        t = _dt.datetime.fromisoformat(str(ts)[:19])
    except Exception:
        return 0
    return max(0, int((now - t).total_seconds() // 86400))


def provenance(source):
    """(weight, note). Exact user allowlist -> 1.0; quick/human-capture -> 0.6; legacy/null -> 0.5
    neutral; every machine/unrecognized source -> 0.3 (so a self-authored 'user-lookalike' can't game it)."""
    s = str(source or "").strip().lower()
    if USER_RE.match(s):
        return 1.0, (s or "user")
    if s.startswith("quick"):
        return 0.6, s
    if s == "":
        return 0.5, "legacy-null"
    return 0.3, s


def score(item, now=None):
    """WSJF-Lite value/size score used ONLY to order items WITHIN one severity band. Returns
    (score, why[]). smaller size -> higher score ('small wins first'). Every term is null-safe."""
    now = now or _dt.datetime.now()
    prio = str(item.get("priority") or "").strip().lower()
    severity = PRIO_SCORE.get(prio, 0.4)
    typ = str(item.get("type") or "task").strip().lower()
    blob = " ".join(str(item.get(k) or "") for k in ("title", "detail", "label", "area"))
    sec_hit = bool(SEC_RE.search(blob))
    time_crit = min(1.0, TYPE_CRIT.get(typ, 0.4) + (0.3 if sec_hit else 0.0))
    prov, prov_note = provenance(item.get("source"))
    enable = 0.0
    if item.get("epic") or item.get("parent"):
        enable += 0.6
    if str(item.get("source") or "").lower().startswith(("decompose", "opus-decompose")):
        enable += 0.4
    enable = min(1.0, enable)
    age_days = _age_days(item.get("created") or item.get("updated"), now)
    aging = min(AGING_CAP, AGING_PER_DAY * age_days)
    eff = str(item.get("effort") or "").strip().upper()
    size = EFFORT_SIZE.get(eff) or TYPE_SIZE.get(typ, 2)
    size += min(4, len(item.get("children") or []))
    size = max(1, size)                       # never 0 (no div-by-zero)
    numerator = (W_SEVERITY * severity + W_TIMECRIT * time_crit
                 + W_PROVENANCE * prov + W_ENABLEMENT * enable + aging)
    sc = round(numerator / size, 5)
    why = [
        {"factor": "severity", "value": round(severity, 3), "weight": W_SEVERITY, "note": prio or "unset"},
        {"factor": "time_criticality", "value": round(time_crit, 3), "weight": W_TIMECRIT,
         "note": typ + (" +sec-kw" if sec_hit else "")},
        {"factor": "provenance", "value": round(prov, 3), "weight": W_PROVENANCE, "note": prov_note},
        {"factor": "enablement", "value": round(enable, 3), "weight": W_ENABLEMENT,
         "note": "child-of-epic" if enable else "standalone"},
        {"factor": "aging", "value": round(aging, 3), "weight": 1.0, "note": "%dd waited" % age_days},
        {"factor": "size(divisor)", "value": size, "weight": 1.0, "note": eff or ("type:" + typ)},
    ]
    return sc, why


def autonomy_gate(item, leased_paths=None):
    """Return a human-readable gatedReason if an autonomous agent must NOT self-pick this item (route it
    to a human/senior lane), else None. ELIGIBILITY, independent of ranking. leased_paths maps a
    filename -> holder for the file-conflict rule."""
    typ = str(item.get("type") or "").strip().lower()
    prio = str(item.get("priority") or "").strip().lower()
    if typ in GATE_TYPES:
        return "type=%s: architecture/research/security is senior-owned" % typ
    if prio == "critical":
        return "priority=critical: severe/likely-irreversible, needs human sign-off"
    blob = " ".join(str(item.get(k) or "") for k in ("title", "detail", "label", "area"))
    m = SEC_RE.search(blob)
    if m:
        return "security-keyword '%s': needs human sign-off" % m.group(0).lower()
    detail = str(item.get("detail") or "")
    if len(detail) < 80 and not (("accept" in detail.lower()) or item.get("children")):
        return "underspecified: detail<80 chars & no acceptance/children"
    low = blob.lower()
    for base, holder in (leased_paths or {}).items():
        if base and str(base).lower() in low:
            return "file-leased by %s (%s): work file-disjoint" % (holder, base)
    return None


def rank(items, actor="watcher", leased_paths=None, limit=None, now=None):
    """Rank a backlog for pickup. Returns {items, gated, total, gatedTotal}.

    BAND-FIRST: sort key = (severity band, -score, created ASC, id ASC). The band is a HARD primary key
    so critical strictly outranks high; the score only reorders within a band; the id tail makes the
    order identical for every parallel actor on the same snapshot (no claim races). For actor in
    {watcher, autodev} the Autonomy Gate routes ineligible work into `gated` (never dropped); any other
    actor (e.g. 'interactive') bypasses the gate."""
    now = now or _dt.datetime.now()
    gate_on = str(actor or "").strip().lower() in GATED_ACTORS
    picks, gated = [], []
    for it in items:
        if str(it.get("status") or "open").strip().lower() not in REVIEW_ELIGIBLE:
            continue
        sc, why = score(it, now)
        rec = dict(it); rec["score"], rec["why"] = sc, why
        reason = autonomy_gate(it, leased_paths) if gate_on else None
        if reason:
            rec["gatedReason"] = reason
            gated.append(rec)
        else:
            picks.append(rec)

    def _epoch(it):
        try:
            return _dt.datetime.fromisoformat(str(it.get("created") or "")[:19]).timestamp()
        except Exception:
            return float("inf")   # null-created sorts last on the age tie-break

    def _key(it):
        return (PRIO_BAND.get(str(it.get("priority") or "").strip().lower(), 2),
                -it.get("score", 0.0), _epoch(it), str(it.get("id") or ""))

    picks.sort(key=_key)
    gated.sort(key=_key)
    return {"items": picks[:limit] if limit else picks, "gated": gated,
            "total": len(picks), "gatedTotal": len(gated)}
