#!/usr/bin/env python3
"""Audience & conversation-retention audit for a Delphi clone (READ-ONLY).

Two "superpowers" in one pass:

  1. AUDIENCE SIZING — total users on file vs. "real" users. Delphi audiences are
     padded with test/smoke/integration emails; the number that matters for any
     real metric is REAL users (fake addresses filtered out). See is_real().

  2. CONVERSATION RETENTION — of the real users who actually started a
     conversation, how many came back? Measured from each conversation's
     `created_at` timestamp (the real return signal, not a yes/no flag):
       - return rate : % of conversers with >=2 conversations
       - multi-day   : % active on >=2 distinct UTC calendar days  (truest signal)
       - recency     : days since each user's LAST conversation (churn watch)
       - depth       : conversations-per-user distribution + outlier flag

STRICTLY GET-only — no users/conversations/tags are created or modified. Paced
under the 120 req/60s limit, with retries on Delphi's intermittent 500s. Sets a
custom User-Agent because Cloudflare 403s the default python-urllib UA.

Usage:
    python3 scripts/audience_audit.py --api-key "$DELPHI_API_KEY"
    python3 scripts/audience_audit.py --account karamo          # from keys.json
    python3 scripts/audience_audit.py --api-key dsk-... --json   # machine-readable
    python3 scripts/audience_audit.py --api-key dsk-... --no-retention  # sizing only
"""

import argparse, datetime, json, os, statistics, sys, time
import urllib.error, urllib.parse, urllib.request

BASE = "https://api.delphi.ai"
UA = "delphi-audience-audit/1.0"  # default python-urllib UA is 403'd by Cloudflare
NOW = datetime.datetime.now(datetime.timezone.utc)

# Substrings that mark an email as non-real (test / integration / placeholder).
FAKE_MARKERS = ("example", "fake", "test", "noinput", "smoke",
                "placeholder", "dummy", "invalid", "@test.", "no-reply", "noreply")


def is_real(email: str) -> bool:
    """A 'real' audience email: has a plausible address and no test/fake marker."""
    if not email or "@" not in email:
        return False
    local, _, domain = email.lower().partition("@")
    if "." not in domain or not local:
        return False
    return not any(m in email.lower() for m in FAKE_MARKERS)


def resolve_key(args) -> str:
    if args.api_key:
        return args.api_key
    if os.environ.get("DELPHI_API_KEY"):
        return os.environ["DELPHI_API_KEY"]
    if args.account:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for path in (os.path.join(root, "keys.json"),
                     os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "keys.json")):
            if os.path.exists(path):
                accounts = json.load(open(path)).get("accounts", {})
                if args.account in accounts:
                    return accounts[args.account]
                sys.exit(f"Account '{args.account}' not found in {path}.")
        sys.exit("No keys.json found for --account lookup.")
    sys.exit("Provide --api-key, set $DELPHI_API_KEY, or pass --account <name>.")


def get(path: str, key: str, retries: int = 5):
    req = urllib.request.Request(f"{BASE}{path}", headers={"x-api-key": key, "User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise


def _day(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except Exception:
        return None


def _ts(ts):
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def sweep_users(key: str) -> list:
    users, cursor = [], None
    while True:
        url = "/v3/users?limit=1000" + (f"&cursor={urllib.parse.quote(cursor, safe='')}" if cursor else "")
        d = get(url, key)
        users.extend(d.get("users", []))
        cursor = d.get("next_cursor")
        print(f"  swept {len(users)} (has_more={d.get('has_more')})", file=sys.stderr)
        if not d.get("has_more") or not cursor:
            return users
        time.sleep(0.4)


def pull_conversations(real_users: list, key: str):
    records, errors = [], []
    for i, u in enumerate(real_users):
        try:
            d = get("/v3/conversation/list?email=" + urllib.parse.quote(u["email"], safe=""), key)
            convos = d.get("conversations") or d.get("data") or []
            records.append({"email": u["email"], "date_joined": u.get("date_joined"),
                            "convos": [{"created_at": c.get("created_at"), "medium": c.get("medium")}
                                       for c in convos]})
        except Exception as e:
            errors.append({"email": u["email"], "error": str(e)})
        if (i + 1) % 75 == 0:
            print(f"  conversations {i+1}/{len(real_users)} (errors {len(errors)})", file=sys.stderr)
        time.sleep(0.18)
    return records, errors


def compute_retention(records: list) -> dict:
    conversers = [r for r in records if r["convos"]]
    nc = len(conversers)
    per_user = [len(r["convos"]) for r in conversers]
    total = sum(per_user)
    returners = sum(1 for n in per_user if n >= 2)
    multiday = sum(1 for r in conversers
                   if len({_day(c["created_at"]) for c in r["convos"] if _day(c["created_at"])}) >= 2)
    buckets = {"1": 0, "2-3": 0, "4-10": 0, "11+": 0}
    for n in per_user:
        buckets["1" if n == 1 else "2-3" if n <= 3 else "4-10" if n <= 10 else "11+"] += 1
    rec = {"<=7d": 0, "8-30d": 0, "31-90d": 0, ">90d": 0}
    for r in conversers:
        times = [_ts(c["created_at"]) for c in r["convos"] if _ts(c["created_at"])]
        if times:
            dd = (NOW - max(times)).total_seconds() / 86400
            rec["<=7d" if dd <= 7 else "8-30d" if dd <= 30 else "31-90d" if dd <= 90 else ">90d"] += 1
    medium = {}
    for r in records:
        for c in r["convos"]:
            m = c.get("medium") or "UNKNOWN"
            medium[m] = medium.get(m, 0) + 1
    return {
        "conversers": nc, "total_conversations": total,
        "mean_per_converser": round(total / nc, 2) if nc else 0,
        "median_per_converser": statistics.median(per_user) if per_user else 0,
        "max_per_user": max(per_user) if per_user else 0,
        "returners_2plus": returners,
        "return_rate": round(returners / nc, 4) if nc else None,
        "multi_day": multiday,
        "multi_day_rate": round(multiday / nc, 4) if nc else None,
        "one_and_done": nc - returners,
        "depth_distribution": buckets,
        "recency_days_since_last": rec,
        "medium_breakdown": medium,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Delphi audience & retention audit (read-only).")
    ap.add_argument("--api-key")
    ap.add_argument("--account", help="Account name in keys.json (e.g. karamo).")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a text report.")
    ap.add_argument("--no-retention", action="store_true", help="Audience sizing only (skip conversation pull).")
    ap.add_argument("--cache", help="Write raw per-user conversation data to this path (PII — keep local).")
    args = ap.parse_args()
    key = resolve_key(args)

    clone = get("/v3/clone", key).get("clone", {})
    name = clone.get("name", "<unknown>")
    print(f"clone: {name} ({clone.get('slug')})", file=sys.stderr)

    print("sweeping users...", file=sys.stderr)
    users = sweep_users(key)
    real = [u for u in users if is_real(u.get("email", ""))]
    report = {
        "clone": name, "generated_at": NOW.isoformat(),
        "audience": {"total_users": len(users), "real_users": len(real),
                     "filtered_out": len(users) - len(real)},
    }

    if not args.no_retention:
        print(f"pulling conversations for {len(real)} real users...", file=sys.stderr)
        records, errors = pull_conversations(real, key)
        report["retention"] = compute_retention(records)
        report["retention"]["unresolved_errors"] = len(errors)
        if args.cache:
            json.dump({"records": records, "errors": errors}, open(args.cache, "w"), default=str)
            print(f"cached raw data -> {args.cache}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
    return 0


def print_report(rep: dict):
    a = rep["audience"]
    print("\n" + "=" * 56)
    print(f"{rep['clone'].upper()} — AUDIENCE & RETENTION   (run {NOW.date()})")
    print("=" * 56)
    print("AUDIENCE")
    print(f"  Total users on file:  {a['total_users']}")
    print(f"  Real users:           {a['real_users']}")
    print(f"  Filtered (test/fake): {a['filtered_out']}")
    r = rep.get("retention")
    if not r:
        return
    nc = r["conversers"]
    pct = lambda x: f"{100*x/nc:.1f}%" if nc else "n/a"
    print(f"\nRETENTION  (base: {nc} real users with >=1 conversation)")
    print(f"  Total conversations:  {r['total_conversations']}")
    print(f"  Median / converser:   {r['median_per_converser']:.0f}   (mean {r['mean_per_converser']}"
          f" — skewed by max {r['max_per_user']}/user)")
    print(f"  Return rate (>=2):    {r['returners_2plus']}  ({pct(r['returners_2plus'])})")
    print(f"  Multi-day (>=2 days): {r['multi_day']}  ({pct(r['multi_day'])})   <- truest retention")
    print(f"  One-and-done:         {r['one_and_done']}  ({pct(r['one_and_done'])})")
    print("  Depth:  " + "  ".join(f"{k}:{v}" for k, v in r["depth_distribution"].items()))
    print("  Recency (days since last convo):  "
          + "  ".join(f"{k}:{v}" for k, v in r["recency_days_since_last"].items()))
    print("  Medium: " + "  ".join(f"{k}:{v}" for k, v in
          sorted(r["medium_breakdown"].items(), key=lambda x: -x[1])))
    if r.get("unresolved_errors"):
        print(f"  Unresolved errors after retries: {r['unresolved_errors']}")


if __name__ == "__main__":
    raise SystemExit(main())
