#!/usr/bin/env python3
"""Clear, correctly-defined D30 retention for a Delphi clone (READ-ONLY).

D30 RETENTION, DEFINED PROPERLY
--------------------------------
"Of users who first showed up in the acquisition half of the window, what %
had another conversation within the following 30 days?"

The window is always the last WINDOW_DAYS (default 60), split into two equal
halves ending at a reference time:

    [reference-60d ... reference-30d)  <- acquisition half (cohort membership)
    [reference-30d ... reference]       <- return-check half

Every cohort member is guaranteed a full 30 days to return before the return-
check half ends at `reference` -- so there is NO CENSORING BIAS (unlike the
2026-08-01 analysis, which had to drop 191 users acquired too recently). By
construction, this is always a clean, repeatable, rolling number.

THREE DATA SOURCES, ONE CALCULATION
------------------------------------
The retention math (`compute_d30`) is a pure function over
{email: [conversation start datetimes]}. Three ways to build that dict:

  --export PATH only        Fast, cheap, uses only the NDJSON export. Caveat:
                             cohort membership is "first appearance IN the
                             export" not true lifetime-first-ever -- a long-
                             lapsed returning user just outside the export
                             window can misclassify as "new."

  --account / --api-key only   Full live sweep: GET /v3/users (paginated) then
                             GET /v3/conversation/list per real user (returns
                             full, uncapped history -- authoritative "first
                             ever" per Delphi's own docs). Most accurate, but
                             does one API call per real user in the ENTIRE
                             audience -- slow on a large clone.

  --export PATH --account X   COMBO (recommended default when both are
                             available): use the export purely to find which
                             users were active in the window (cheap, local),
                             then hit the live API ONLY for those candidates
                             to pull their authoritative full history. Also
                             does one cheap GET /v3/users sweep to report
                             audience COVERAGE -- how much of the live real
                             audience the export actually captured. Gets
                             API-grade accuracy at export-mode cost.

Usage:
    python3 scripts/d30_retention.py --export conversations.ndjson
    python3 scripts/d30_retention.py --account david_kessler
    python3 scripts/d30_retention.py --export conversations.ndjson --account david_kessler
    python3 scripts/d30_retention.py --export conversations.ndjson --account david_kessler --window-days 90 --json
"""
import argparse, datetime, json, os, sys, time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audience_audit as aa  # reuse resolve_key / get / sweep_users / is_real / retry+pacing

FAKE_MARKERS = aa.FAKE_MARKERS
DEFAULT_EXCLUDE = {"support@delphi.ai"}  # Delphi's placeholder for anonymous embed sessions --
                                          # NOT a real repeat visitor; extend with --exclude-email

# Legacy dsk- keys are capped at 120 req/60s (~2 req/s). App-Launch dlph_ keys carry a much
# higher published cap (10k req/min), so pace them faster -- but pace them, not zero-delay:
# a rapid burst has been observed to draw a 429 even on a dlph_ key, so this is "safely fast,"
# not "unlimited." Per-user history pulls (combo/api modes) are the only place volume matters.
PACE_SECONDS = {"applaunch": 0.05, "legacy": 0.6}


def key_style(key: str) -> str:
    return "applaunch" if key.startswith("dlph_") else "legacy"


def resolve_key_preferring_applaunch(args) -> tuple:
    """Resolve the API key for --account/--api-key, auto-upgrading to a sibling
    `<account>_applaunch` key in keys.json when one exists and a plain account
    name was given (not already dlph_) -- so bulk pulls default to the high-rate-
    limit key without the caller having to know the exact handle."""
    explicit = args.api_key or os.environ.get("DELPHI_API_KEY")
    if explicit:
        if key_style(explicit) == "legacy":
            print("NOTE: this is a legacy dsk- key (120 req/60s cap). If a dlph_ App-Launch "
                  "key exists for this clone, pass it instead for faster/safer bulk pulls.",
                  file=sys.stderr)
        return explicit, key_style(explicit)

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    keys_path = os.path.join(root, "keys.json")
    accounts = json.load(open(keys_path)).get("accounts", {}) if os.path.exists(keys_path) else {}

    base_key = accounts.get(args.account)
    if base_key is None:
        sys.exit(f"Account '{args.account}' not found in {keys_path}.")

    if key_style(base_key) == "legacy":
        sibling = f"{args.account}_applaunch"
        if sibling in accounts and key_style(accounts[sibling]) == "applaunch":
            print(f"NOTE: '{args.account}' is a legacy dsk- key; auto-upgrading to the "
                  f"higher-rate-limit '{sibling}' (dlph_) key for this run.", file=sys.stderr)
            return accounts[sibling], "applaunch"
        print(f"NOTE: '{args.account}' is a legacy dsk- key (120 req/60s cap) and no "
              f"'{sibling}' App-Launch key exists yet. Pacing conservatively.", file=sys.stderr)
    return base_key, key_style(base_key)


def is_real(email: str, extra_exclude: set) -> bool:
    if not email or email.lower() in extra_exclude:
        return False
    return aa.is_real(email)


def parse_ts(s):
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------- sources --

def load_from_export(path: str, exclude: set) -> dict:
    """NDJSON: one thread per line -> {email: [conversation start datetimes]}."""
    by_user = {}
    total_threads = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total_threads += 1
            t = json.loads(line)
            email = t.get("user_email", "")
            if not is_real(email, exclude):
                continue
            times = [parse_ts(m.get("created_at")) for m in t.get("messages", [])]
            times = [x for x in times if x]
            if not times:
                continue
            by_user.setdefault(email, []).append(min(times))
    for e in by_user:
        by_user[e].sort()
    return by_user, total_threads


def load_from_api_full(key: str, exclude: set, style: str, verbose=True) -> dict:
    """Full live sweep: every real user's full conversation history."""
    pace = PACE_SECONDS[style]
    if verbose:
        print("sweeping full live audience...", file=sys.stderr)
    users = aa.sweep_users(key)
    real = [u for u in users if is_real(u.get("email", ""), exclude)]
    if verbose:
        print(f"pulling full history for {len(real)} real users... (pace={pace}s, key={style})", file=sys.stderr)
    by_user = {}
    for i, u in enumerate(real):
        email = u["email"]
        try:
            d = aa.get("/v3/conversation/list?email=" + urllib.parse.quote(email, safe=""), key)
            convos = d.get("conversations") or d.get("data") or []
            times = [parse_ts(c.get("created_at")) for c in convos]
            times = sorted(x for x in times if x)
            if times:
                by_user[email] = times
        except Exception:
            pass
        if verbose and (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(real)}", file=sys.stderr)
        time.sleep(pace)
    return by_user, len(users), len(real)


def load_api_for_emails(emails: list, key: str, style: str, verbose=True) -> dict:
    """Authoritative full history for a SPECIFIC candidate list (combo mode)."""
    pace = PACE_SECONDS[style]
    by_user = {}
    if verbose:
        print(f"pulling authoritative history for {len(emails)} candidate users... (pace={pace}s, key={style})", file=sys.stderr)
    for i, email in enumerate(emails):
        try:
            d = aa.get("/v3/conversation/list?email=" + urllib.parse.quote(email, safe=""), key)
            convos = d.get("conversations") or d.get("data") or []
            times = [parse_ts(c.get("created_at")) for c in convos]
            times = sorted(x for x in times if x)
            if times:
                by_user[email] = times
        except Exception:
            pass
        if verbose and (i + 1) % 100 == 0:
            print(f"  {i+1}/{len(emails)}", file=sys.stderr)
        time.sleep(pace)
    return by_user


# ------------------------------------------------------------- calculation --

def compute_d30(by_user: dict, reference_time: datetime.datetime, window_days: int = 60) -> dict:
    half = window_days / 2
    window_start = reference_time - datetime.timedelta(days=window_days)  # full window back
    mid = reference_time - datetime.timedelta(days=half)                  # boundary between the two halves

    cohort = {e: t for e, t in by_user.items() if t and window_start <= t[0] < mid}
    retained_emails = []
    for e, times in cohort.items():
        day0 = times[0]
        cutoff30 = day0 + datetime.timedelta(days=half)
        if any(day0 < t <= cutoff30 for t in times[1:]):
            retained_emails.append(e)

    n = len(cohort)
    r = len(retained_emails)
    return {
        "reference_time": reference_time.isoformat(),
        "window_days": window_days,
        "acquisition_half": [window_start.isoformat(), mid.isoformat()],
        "return_check_half": [mid.isoformat(), reference_time.isoformat()],
        "cohort_size": n,
        "retained": r,
        "d30_rate_pct": round(r / n * 100, 1) if n else None,
        "retained_emails": retained_emails,
    }


def top_engaged(by_user, n=10):
    rows = sorted(by_user.items(), key=lambda kv: -len(kv[1]))[:n]
    out = []
    for email, times in rows:
        masked = (email[0] + "***@" + email.split("@")[-1]) if "@" in email else email
        out.append({"email_masked": masked, "conversations": len(times), "last_seen": times[-1].isoformat()})
    return out


# ------------------------------------------------------------------- main --

def main():
    ap = argparse.ArgumentParser(description="Clear, censoring-corrected D30 retention (read-only).")
    ap.add_argument("--export", help="NDJSON conversation export path.")
    ap.add_argument("--api-key")
    ap.add_argument("--account", help="Account name in keys.json.")
    ap.add_argument("--window-days", type=int, default=60, help="Total rolling window (split 50/50). Default 60.")
    ap.add_argument("--exclude-email", action="append", default=[], help="Additional placeholder email(s) to exclude (repeatable).")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    exclude = DEFAULT_EXCLUDE | {e.lower() for e in args.exclude_email}
    key, style = None, None
    if args.api_key or args.account:
        key, style = resolve_key_preferring_applaunch(args)

    if not args.export and not key:
        sys.exit("Provide --export, and/or --account/--api-key.")

    coverage = None
    if args.export and key:
        mode = "combo"
        export_by_user, total_threads = load_from_export(args.export, exclude)
        # cheap full-audience sweep, for coverage reporting only (no per-user pulls here)
        print("sweeping live audience for coverage check...", file=sys.stderr)
        live_users = aa.sweep_users(key)
        live_real = {u["email"] for u in live_users if is_real(u.get("email", ""), exclude)}
        candidates = list(export_by_user.keys())
        by_user = load_api_for_emails(candidates, key, style)
        coverage = {
            "live_real_audience": len(live_real),
            "export_active_users": len(export_by_user),
            "coverage_pct": round(len(export_by_user) / len(live_real) * 100, 1) if live_real else None,
            "registered_but_absent_from_export": len(live_real - set(export_by_user.keys())),
        }
        reference_time = datetime.datetime.now(datetime.timezone.utc)
    elif args.export:
        mode = "export-only"
        by_user, total_threads = load_from_export(args.export, exclude)
        all_times = [t for times in by_user.values() for t in times]
        reference_time = max(all_times) if all_times else datetime.datetime.now(datetime.timezone.utc)
    else:
        mode = "api-only"
        by_user, total_live, total_real = load_from_api_full(key, exclude, style)
        reference_time = datetime.datetime.now(datetime.timezone.utc)

    result = compute_d30(by_user, reference_time, args.window_days)
    result["mode"] = mode
    if style:
        result["key_style"] = style
    if coverage:
        result["coverage"] = coverage
    result["top_engaged"] = top_engaged(by_user, args.top)
    result.pop("retained_emails")  # PII -- not for default output

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("=" * 72)
    style_note = f"  key: {style} ({'App-Launch, high rate limit' if style == 'applaunch' else 'legacy, 120 req/60s cap'})" if style else ""
    print(f"D30 RETENTION  [mode: {mode}]{style_note}")
    print("=" * 72)
    print(f"  Reference time (window end) ... {result['reference_time']}")
    print(f"  Window ......................... {result['window_days']} days "
          f"({result['window_days']//2}d acquisition + {result['window_days']//2}d return-check)")
    if coverage:
        print(f"\n  COVERAGE (export vs live audience):")
        print(f"    Live real audience (API) ....... {coverage['live_real_audience']}")
        print(f"    Active in export window ......... {coverage['export_active_users']}")
        print(f"    Coverage ......................... {coverage['coverage_pct']}%")
        print(f"    Registered but silent in export .. {coverage['registered_but_absent_from_export']}")
    print(f"\n  Cohort (first conversation in acquisition half) ... {result['cohort_size']}")
    print(f"  Returned within 30 days ............................ {result['retained']}")
    print(f"\n  >>> D30 RETENTION RATE = {result['retained']}/{result['cohort_size']} = {result['d30_rate_pct']}%")
    print(f"\n  Top {len(result['top_engaged'])} most-engaged users in this data:")
    for row in result["top_engaged"]:
        print(f"    {row['email_masked']:<28} {row['conversations']:>3} convos   last seen {row['last_seen'][:10]}")


if __name__ == "__main__":
    main()
