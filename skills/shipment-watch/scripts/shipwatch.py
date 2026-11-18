#!/usr/bin/env python3
"""shipwatch.py - watch a vendor's public "shipping dashboard" for the batch that covers your order,
and estimate when it will ship. Stdlib only, ASCII only, UTF-8 IO.

Many direct-to-consumer hardware vendors publish a page that lists, per date, which ranges of order
numbers have shipped for each product variant, e.g.

    2026/11/14
    Gadget 3 Pro Black: 3214xx--3237xx

meaning orders of that variant whose number starts 3214..3237 shipped that day. This tool parses
such a page, finds the rows for your product, compares your order's LEADING DIGITS to each batch
range, and tells you: shipped / possibly shipped / still waiting, plus how far shipping has got.

Commands
  parse  PAGE                      print every parsed batch row as JSON (PAGE = file path or URL)
  check  --config C --state S      one watch tick: fetch if due, evaluate, notify once per event,
                                   retry failed notifications, self-disarm on ship/expiry
         [--page FILE] [--force] [--notify-cmd CMD] [--test]
  eta    --config C [--page FILE]  estimate the ship and arrival window from the dashboard history
         [--order-date YYYY-MM-DD] [--rate UNITS_PER_DAY] [--transit 3-7]

Config (JSON):
  {"id": "vendor-gadget3", "url": "https://vendor.example/pages/shipping-dashboard",
   "order": "AB3352817", "product": "Gadget 3", "tier": "base", "color": "black",
   "tiers": ["base", "lite", "pro", "max"], "colors": ["black", "white", "grey", "gray"],
   "safe_words": ["gadget"], "expires": "2027-03-31", "interval_sec": 3600}

Notifications are delivered by --notify-cmd: a command that receives one JSON object
{"kind", "urgent", "subject", "body"} on stdin and exits 0 on success. Without it, messages are
printed. Every word in a message comes from this tool's own labels, digits, dates, or the config's
whitelisted words -- never raw page text -- so the page cannot steer what gets sent.
"""
import argparse
import datetime as _dt
import html as _html
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

DEFAULT_TIERS = ["base", "lite", "pro", "max", "ultra", "plus", "mini"]
DEFAULT_COLORS = ["black", "white", "grey", "gray", "blue", "purple", "green", "red", "pink",
                  "clear", "silver", "orange", "yellow", "cold", "rainbow"]
DATE_RE = re.compile(r"^(20\d{2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{1,2})$")
# "<name>: 3214xx--3237xx"; tolerates full-width colon, en/em dashes, tildes, "to"
ROW_RE = re.compile(
    r"^(?P<name>[^:\uFF1A]{3,120}?)\s*[:\uFF1A]\s*(?P<a>\d{3,7})\s*x+\s*"
    r"(?:(?:-|\u2013|\u2014|~|\uFF5E|to)\s*)+(?P<b>\d{3,7})\s*x+", re.I)
UA = "Mozilla/5.0 (compatible; shipwatch/1.0)"
EMAIL_MAX_ATTEMPTS = 12
RETRY_SECS = 1800
BROKEN_AFTER_ERRORS = 6
BROKEN_REALERT_SECS = 3 * 86400


# ---- parsing (pure) -------------------------------------------------------------------------------
def page_lines(raw):
    """Visible text of an HTML page, one block element per line. Script/style text is dropped, so a
    range hidden in a <script> or template never counts as shipped."""
    s = re.sub(r"(?is)<(script|style|noscript|template)[^>]*>.*?</\1>", " ", raw or "")
    s = re.sub(r"(?i)<br\s*/?>|</?(p|div|li|h\d|tr|td|section|article|header|footer|nav|main|ul|ol|"
               r"table|body|html)\b[^>]*>", "\n", s)
    s = _html.unescape(re.sub(r"<[^>]+>", " ", s))
    return [ln for ln in (re.sub(r"\s+", " ", x).strip() for x in s.split("\n")) if ln]


def parse_dashboard(raw):
    """-> [{date, name, a, b}]. a/b stay digit STRINGS: their length says how many leading order
    digits they stand for ('3214' in '3214xx' = the first four digits)."""
    rows, date = [], None
    for line in page_lines(raw):
        md = DATE_RE.match(line)
        if md:
            try:
                date = _dt.date(*(int(x) for x in md.groups())).isoformat()
            except ValueError:
                date = None
            continue
        mr = ROW_RE.match(line)
        if mr:
            rows.append({"date": date, "name": mr.group("name").strip(), "a": mr.group("a"), "b": mr.group("b")})
    return rows


def unparsed_row_like(raw):
    """Visible lines that carry an 'NNNNxx' batch number but did NOT parse as a row. Run this after
    the vendor changes the page: an empty list means no batch line is being silently skipped."""
    return [ln[:120] for ln in page_lines(raw)
            if re.search(r"\d{3,7}\s*x{2,}", ln, re.I) and not ROW_RE.match(ln)]


def tokens(name):
    n = (name or "").lower()
    n = re.sub(r"([a-z])(\d)", r"\1 \2", n)      # gadget3 -> gadget 3
    n = re.sub(r"(\d)([a-z])", r"\1 \2", n)      # 512gb -> 512 gb
    return re.findall(r"[a-z]+|\d+", n)


def _words(cfg):
    tiers = set(cfg.get("tiers") or DEFAULT_TIERS)
    colors = set(cfg.get("colors") or DEFAULT_COLORS)
    return tiers, colors


def safe_name(name, cfg):
    """Whitelisted words + numbers only. This is all of the page that may reach a notification."""
    tiers, colors = _words(cfg)
    ok = tiers | colors | set(tokens(cfg.get("product", ""))) | {w.lower() for w in cfg.get("safe_words", [])}
    out = [t if t.isdigit() else t.capitalize() for t in tokens(name) if t.isdigit() or t in ok]
    return " ".join(out)[:60]


def classify(name, cfg):
    """None = not this product; 'exact' = the watched tier+colour; 'ambiguous' = this product with no
    tier word and a compatible colour (could be yours); 'other' = another variant of the product."""
    t = tokens(name)
    p = tokens(cfg["product"])
    if not any(t[i:i + len(p)] == p for i in range(len(t) - len(p) + 1)):
        return None
    ts = set(t)
    if ts & {w.lower() for w in cfg.get("exclude_words", [])}:   # e.g. "portal" when watching the plain model
        return None
    tiers, colors = _words(cfg)
    row_tiers, row_colors = ts & tiers, ts & colors
    want_tier, want_color = (cfg.get("tier") or "").lower(), (cfg.get("color") or "").lower()
    tier_match = (row_tiers == {want_tier}) if want_tier else True
    tier_unknown = bool(want_tier) and not row_tiers
    color_match = (want_color in ts) if want_color else True
    color_unknown = bool(want_color) and not row_colors
    if tier_match and color_match:
        return "exact"
    if (tier_match or tier_unknown) and (color_match or color_unknown):
        return "ambiguous"
    return "other"


def order_digits(cfg):
    return re.sub(r"\D", "", str(cfg["order"]))


def _lead(digits, n):
    return int(digits[:n]) if len(digits) >= n else None


def passed(row, digits):
    """The batch's upper bound reached the order: shipping for that variant is at or past it."""
    k = _lead(digits, len(row["b"]))
    return k is not None and k <= int(row["b"])


def covers(row, digits):
    k = _lead(digits, len(row["a"]))
    return passed(row, digits) and k is not None and k >= int(row["a"])


def _public(r, cfg):
    if not r:
        return None
    return {"date": r.get("date"), "variant": safe_name(r["name"], cfg), "cls": r.get("cls"),
            "range": "%sxx-%sxx" % (r["a"], r["b"]), "covers": r.get("covers")}


def _frontier(rs, cfg):
    if not rs:
        return None
    top = max(rs, key=lambda r: (len(r["b"]), int(r["b"]), r.get("date") or ""))
    return {"upTo": "%sxx" % top["b"], "date": top.get("date"), "variant": safe_name(top["name"], cfg)}


def evaluate(rows, cfg):
    """status: 'shipped' (an exact-variant batch reached the order) | 'possible' (a tier-less batch of
    the product reached it) | 'waiting'."""
    digits = order_digits(cfg)
    prod = []
    for r in rows:
        c = classify(r["name"], cfg)
        if c:
            prod.append(dict(r, cls=c, covers=covers(r, digits), passed=passed(r, digits)))
    exact = [r for r in prod if r["cls"] == "exact"]
    shipped = [r for r in exact if r["passed"]]
    possible = [r for r in prod if r["cls"] == "ambiguous" and r["passed"]]
    other_passed = [r for r in prod if r["cls"] == "other" and r["passed"]]
    status = "shipped" if shipped else ("possible" if possible else "waiting")
    pick = shipped or possible
    match = sorted(pick, key=lambda r: (not r["covers"], r.get("date") or ""))[0] if pick else None
    return {"status": status, "orderLead": digits[:4], "rowsTotal": len(rows), "productRows": len(prod),
            "exactRows": len(exact), "exactFrontier": _frontier(exact, cfg),
            "productFrontier": _frontier(prod, cfg), "match": _public(match, cfg),
            "otherPassed": [_public(r, cfg) for r in other_passed][:5]}


# ---- messages: built from our labels + parsed digits/dates/whitelisted words only -------------------
def _label(cfg):
    return " ".join(x for x in (cfg.get("vendor", ""), cfg["product"]) if x)


def _variant(cfg):
    return cfg.get("variant") or " ".join(x for x in (cfg.get("tier", ""), cfg.get("color", "")) if x) or "your variant"


def msg_shipped(cfg, ev, test=False):
    m = ev.get("match") or {}
    pre = "[TEST] " if test else ""
    where = "inside" if m.get("covers") else "at or below the top of"
    body = []
    if test:
        body += ["TEST of the shipment watch: the 'shipped' batch below was injected into today's real",
                 "page to exercise fetch, parse, match and delivery. Nothing has actually shipped.", ""]
    body += ["Order %s (%s %s) now shows as shipped on the vendor's shipping dashboard." % (
                 cfg["order"], _label(cfg), _variant(cfg)),
             "Batch: %s, %s orders %s." % (m.get("date") or "date not shown", m.get("variant"), m.get("range")),
             "Your order starts %s, which is %s that range." % (ev.get("orderLead"), where), "",
             "Tracking numbers usually arrive separately, often a day or two after the dashboard update.",
             "Dashboard: %s" % cfg["url"], "",
             "- shipment watch. " + ("Test only; the watch is still running." if test else
                                     "This watch has now switched itself off.")]
    return {"kind": "shipped", "urgent": True, "subject": pre + "%s order %s has shipped" % (_label(cfg), cfg["order"]),
            "body": "\n".join(body)}


def msg_possible(cfg, ev):
    m = ev.get("match") or {}
    return {"kind": "possible", "urgent": True,
            "subject": "%s order %s may have shipped" % (_label(cfg), cfg["order"]),
            "body": "\n".join([
                "The dashboard lists a %s batch that names no model tier: %s on %s, orders %s." % (
                    _label(cfg), m.get("variant"), m.get("date") or "date not shown", m.get("range")),
                "Your order %s starts %s, so this batch may include it." % (cfg["order"], ev.get("orderLead")),
                "Please check: %s" % cfg["url"], "",
                "- shipment watch. Still watching for a batch that names your exact variant."])}


def msg_info(cfg, kind, ev):
    if kind == "exactStarted":
        f = ev["exactFrontier"]
        text = "First batches for %s %s: up to %s (%s). Your order starts %s." % (
            _label(cfg), _variant(cfg), f["upTo"], f["date"], ev["orderLead"])
    else:
        o = ev["otherPassed"][0]
        text = "%s shipped %s (%s), past your order number; still waiting for %s." % (
            o["variant"], o["range"], o["date"], _variant(cfg))
    return {"kind": kind, "urgent": False, "subject": "%s: shipping progress" % _label(cfg), "body": text}


def _clean_err(e):
    return re.sub(r"[^A-Za-z0-9 .,:_()/-]", "", str(e))[:160]


def msg_broken(cfg, err):
    return {"kind": "broken", "urgent": True,
            "subject": "Shipment watch for order %s can't read the dashboard" % cfg["order"],
            "body": "The watch has failed to read the shipping dashboard for a while.\nLast error: %s\n"
                    "It keeps retrying; until it recovers you will not get a shipped alert.\nDashboard: %s"
                    % (_clean_err(err), cfg["url"])}


def msg_expired(cfg):
    return {"kind": "expired", "urgent": True,
            "subject": "Shipment watch for order %s ended" % cfg["order"],
            "body": "The watch reached its end date (%s) without seeing order %s in a shipped batch and has "
                    "switched itself off.\nDashboard: %s" % (cfg["expires"], cfg["order"], cfg["url"])}


# ---- I/O ------------------------------------------------------------------------------------------
def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise IOError("HTTP %s" % r.status)
        return r.read(5_000_000).decode("utf-8", "replace")


def read_page(src):
    if re.match(r"(?i)https?://", src or ""):
        return fetch(src)
    with open(src, encoding="utf-8", errors="replace") as f:
        return f.read()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, type(default)) else default
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def deliver(msg, notify_cmd):
    """-> (ok, error). Without a command the message is printed and counts as delivered."""
    if not notify_cmd:
        print("NOTIFY [%s] %s\n%s\n" % (msg["kind"], msg["subject"], msg["body"]))
        return True, None
    try:
        cp = subprocess.run(notify_cmd, shell=True, input=json.dumps(msg), capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=300)
    except Exception as e:
        return False, _clean_err(e)
    return (cp.returncode == 0), (None if cp.returncode == 0 else _clean_err((cp.stderr or cp.stdout)[-160:]))


# ---- one tick ----------------------------------------------------------------------------------------
def _now_iso(ts):
    return _dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _notify(st, msg, now):
    st["notified"][msg["kind"]] = _now_iso(now)
    st["outbox"].append(dict(msg, attempts=0, lastTry=0, lastError=None))


def _flush(st, now, notify_cmd, force=False):
    sent = []
    for item in list(st["outbox"]):
        if not force and item["lastTry"] and now - item["lastTry"] < RETRY_SECS:
            continue
        ok, err = deliver(item, notify_cmd)
        item["lastTry"], item["attempts"] = now, item["attempts"] + 1
        if ok:
            st["outbox"].remove(item)
            sent.append(item["kind"])
        else:
            item["lastError"] = err
            if item["attempts"] >= EMAIL_MAX_ATTEMPTS:
                st["outbox"].remove(item)
                st.setdefault("dropped", []).append({"kind": item["kind"], "error": err})
    return sent


def check(cfg, state_path, page=None, force=False, notify_cmd=None, now=None, test=False):
    """One watch tick. Cheap when nothing is due. Persists state before delivering, so a crash mid-send
    never loses the event, and the event is recorded exactly once."""
    now = time.time() if now is None else now
    st = load_json(state_path, {})
    for k, v in (("status", "watching"), ("lastCheck", 0), ("notified", {}), ("outbox", [])):
        st.setdefault(k, v)
    interval = float(cfg.get("interval_sec", 3600))
    out = {"id": cfg.get("id"), "status": st["status"]}
    due = force or test or (st["status"] == "watching" and now - st["lastCheck"] >= interval)
    if due:
        if test:
            st = json.loads(json.dumps(st))       # test runs never touch persisted state
            st["status"], st["notified"], st["outbox"] = "watching", {}, []
        st["lastCheck"] = now
        if st["status"] == "watching" and not test and _dt.date.today().isoformat() > cfg.get("expires", "9999"):
            st["status"] = "expired"
            _notify(st, msg_expired(cfg), now)
        elif st["status"] == "watching":
            try:
                raw = read_page(page or cfg["url"])
                if test:
                    lead = int(order_digits(cfg)[:4])
                    raw += "<p>%s</p><p>%s %s %s: %dxx--%dxx</p>" % (
                        _dt.date.today().strftime("%Y/%m/%d"), cfg["product"], cfg.get("tier", ""),
                        cfg.get("color", ""), lead - 3, lead + 4)
                rows = parse_dashboard(raw)
                if not rows:
                    raise ValueError("no shipment batches found; the page layout may have changed")
            except Exception as e:
                st["lastError"] = _clean_err(e)
                st["consecutiveErrors"] = int(st.get("consecutiveErrors") or 0) + 1
                if (st["consecutiveErrors"] >= BROKEN_AFTER_ERRORS
                        and now - float(st.get("brokenAt") or 0) >= BROKEN_REALERT_SECS):
                    st["brokenAt"] = now
                    _notify(st, msg_broken(cfg, e), now)
                out["error"] = st["lastError"]
            else:
                st["lastError"], st["consecutiveErrors"] = None, 0
                ev = evaluate(rows, cfg)
                st["lastResult"], out["evaluation"] = ev, ev
                if ev["status"] == "shipped":
                    st["status"] = "shipped" if not test else "watching"
                    _notify(st, msg_shipped(cfg, ev, test=test), now)
                else:
                    if ev["status"] == "possible" and not st["notified"].get("possible"):
                        _notify(st, msg_possible(cfg, ev), now)
                    if ev["exactRows"] and not st["notified"].get("exactStarted"):
                        _notify(st, msg_info(cfg, "exactStarted", ev), now)
                    if ev["otherPassed"] and not st["notified"].get("otherPassed"):
                        _notify(st, msg_info(cfg, "otherPassed", ev), now)
        if not test:
            save_json(state_path, st)              # persist the event BEFORE the slow delivery
    if st["outbox"]:
        out["delivered"] = _flush(st, now, notify_cmd, force=force or test)
        if not test:
            save_json(state_path, st)
    out["status"], out["outbox"] = st["status"], len(st["outbox"])
    return out


# ---- ETA estimate ---------------------------------------------------------------------------------------
def estimate(rows, cfg, order_date=None, rate=None, transit=(3, 7)):
    """Rough ship/arrival window from the dashboard's own history. Units are 'batch units': one step of
    the batch number (e.g. one '3214xx' = one hundred orders when batches are written with xx).

    gap   = order lead - furthest batch of the product (units still ahead of you)
    pace  = how fast the product's frontier moved per day between its first and last dated rows
    days  = gap / pace, from the latest row date; jumps happen when stock lands, so the optimistic
            case is 'next big batch'. Everything here is inference -- say so in the answer."""
    digits = order_digits(cfg)
    prod = [r for r in rows if classify(r["name"], cfg) and r.get("date")]
    out = {"productRows": len(prod), "assumptions": []}
    if not prod:
        out["note"] = "no dated rows for this product yet - no pace to extrapolate from"
        return out
    n = max(len(r["b"]) for r in prod)
    lead = _lead(digits, n)
    by_date = {}
    for r in prod:
        if len(r["b"]) == n:
            by_date[r["date"]] = max(by_date.get(r["date"], 0), int(r["b"]))
    dates = sorted(by_date)
    frontier, running = [], 0
    for d in dates:
        running = max(running, by_date[d])
        frontier.append((d, running))
    first_d, first_v = frontier[0]
    last_d, last_v = frontier[-1]
    span = (_dt.date.fromisoformat(last_d) - _dt.date.fromisoformat(first_d)).days
    start_v = min(int(r["a"]) for r in prod if len(r["a"]) == n) if any(len(r["a"]) == n for r in prod) else first_v
    gap = (lead or 0) - last_v
    out.update({"orderLead": lead, "frontier": last_v, "frontierDate": last_d, "gapUnits": gap,
                "firstBatchStart": start_v})
    if gap <= 0:
        out["note"] = "the product frontier is already at or past this order - check the exact variant rows"
        return out
    if span <= 0:
        out["note"] = "only one dated batch so far - pace unknown; re-run after the next update"
        return out
    pace = (last_v - start_v) / float(span + 1)     # units cleared per day, launch batch included
    out["paceUnitsPerDay"] = round(pace, 2)
    if rate:
        out["daysOfOrdersAhead"] = round(gap / float(rate), 1)
        out["assumptions"].append("order rate %.1f units/day supplied by caller" % rate)
    if order_date and rate:
        out["assumptions"].append("order numbers are store-wide and sequential")
    days = gap / pace if pace > 0 else None
    base = _dt.date.fromisoformat(last_d)
    if days is not None:
        lo, hi = days * 0.75, days * 1.5
        ship_lo, ship_hi = base + _dt.timedelta(days=round(lo)), base + _dt.timedelta(days=round(hi))
        out["likelyShip"] = [ship_lo.isoformat(), ship_hi.isoformat()]
        out["likelyArrive"] = [(ship_lo + _dt.timedelta(days=transit[0])).isoformat(),
                               (ship_hi + _dt.timedelta(days=transit[1] + 2)).isoformat()]
        out["assumptions"].append("pace holds at the product's average so far (+/- range 0.75x..1.5x)")
        out["assumptions"].append("transit %d-%d business days, weekends padded" % transit)
    out["optimistic"] = "one large batch once stock lands can clear the whole gap in a day"
    return out


# ---- CLI --------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="Watch a vendor shipping dashboard for your order.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse")
    p.add_argument("page")
    p.add_argument("--audit", action="store_true",
                   help="instead list visible lines that LOOK like batch rows but did not parse")
    c = sub.add_parser("check")
    c.add_argument("--config", required=True)
    c.add_argument("--state", required=True)
    c.add_argument("--page", help="read this file/URL instead of the config url")
    c.add_argument("--force", action="store_true", help="check now even if not due")
    c.add_argument("--notify-cmd", help="command that receives one JSON message on stdin")
    c.add_argument("--test", action="store_true",
                   help="inject a covering batch into the live page and deliver a [TEST] message; state untouched")
    e = sub.add_parser("eta")
    e.add_argument("--config", required=True)
    e.add_argument("--page")
    e.add_argument("--order-date")
    e.add_argument("--rate", type=float, help="order rate in batch units per day, if you can infer it")
    e.add_argument("--transit", default="3-7", help="business days in transit, e.g. 3-7")
    a = ap.parse_args(argv)

    if a.cmd == "parse":
        raw = read_page(a.page)
        if a.audit:
            missed = unparsed_row_like(raw)
            print(json.dumps({"rows": len(parse_dashboard(raw)), "unparsedRowLike": missed}, indent=2))
            return 1 if missed else 0
        print(json.dumps(parse_dashboard(raw), indent=2))
        return 0
    cfg = load_json(a.config, {})
    if not cfg.get("order") or not cfg.get("product") or not (cfg.get("url") or a.page):
        print("config needs at least order, product and url", file=sys.stderr)
        return 2
    if a.cmd == "check":
        print(json.dumps(check(cfg, a.state, page=a.page, force=a.force, notify_cmd=a.notify_cmd, test=a.test),
                         indent=2))
        return 0
    lo, _, hi = a.transit.partition("-")
    rows = parse_dashboard(read_page(a.page or cfg["url"]))
    print(json.dumps(estimate(rows, cfg, a.order_date, a.rate, (int(lo), int(hi or lo))), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
