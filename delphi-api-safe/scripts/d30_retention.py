#!/usr/bin/env python3
"""Clear, correctly-defined D30 retention for a Delphi clone (READ-ONLY).

D30 RETENTION, DEFINED PROPERLY
--------------------------------
"Of users whose FIRST-EVER conversation fell in the acquisition span, what %
had another conversation within RETURN_DAYS of that first one?"

The acquisition span and the return horizon are separate knobs:

    acquisition span = [reference - WINDOW_DAYS, reference - RETURN_DAYS)
    retained         = came back within RETURN_DAYS of their own first visit

    60d window / 30d return -> 30d acquisition span   (default)
    90d window / 30d return -> 60d acquisition span   (~2x the cohort)

Every cohort member is guaranteed a full RETURN_DAYS before `reference`, so
there is NO CENSORING BIAS at any window width.

WIDENING THE WINDOW REQUIRES WIDENING THE EXPORT
------------------------------------------------
D30 cohorts are small because only a slice of active users are brand new.
Widening the acquisition span is the cheapest fix -- but ONLY if the export
covers the wider span too.

In combo/export mode the candidate list comes from the export. Anyone first
seen before the export begins is visible only BECAUSE they came back, i.e. a
survivor, and their retention is wildly inflated. Measured on one clone at a
90-day window: users first seen inside the export returned at 30.3%, users
first seen before it returned at 87.1% -- same run, same definition.

So: to report D30 over a 60-day acquisition span, pull a 90-day export. Do not
just pass --window-days 90 against a 60-day file. main() warns when you do.

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

def compute_d30(by_user: dict, reference_time: datetime.datetime, window_days: int = 60,
                return_days: int = 30) -> dict:
    """Cohort return rate with the acquisition window DECOUPLED from the return horizon.

    acquisition window = [reference - window_days, reference - return_days)
    a user is retained if they came back within `return_days` of their own first visit

    Every cohort member is guaranteed a full `return_days` before `reference`, so
    there is no censoring bias regardless of how wide the acquisition window is.

    Widening `window_days` while holding `return_days` at 30 is the cheapest way to
    grow a D30 cohort: a 60-day window gives 30 days of acquisition, a 90-day window
    gives 60 -- roughly double the cohort for the same, still-honest D30 definition.

    (An earlier version split the window in half and used that half as BOTH the
    acquisition span and the return horizon, so --window-days 90 silently produced
    a 45-day return horizon while still labelling the result "d30". Fixed.)
    """
    if return_days >= window_days:
        raise ValueError(f"return_days ({return_days}) must be < window_days ({window_days}); "
                         "otherwise the acquisition window is empty.")

    window_start = reference_time - datetime.timedelta(days=window_days)
    acq_end = reference_time - datetime.timedelta(days=return_days)

    cohort = {e: t for e, t in by_user.items() if t and window_start <= t[0] < acq_end}
    retained_emails = []
    for e, times in cohort.items():
        day0 = times[0]
        cutoff = day0 + datetime.timedelta(days=return_days)
        if any(day0 < t <= cutoff for t in times[1:]):
            retained_emails.append(e)

    n = len(cohort)
    r = len(retained_emails)
    return {
        "reference_time": reference_time.isoformat(),
        "window_days": window_days,
        "return_days": return_days,
        "acquisition_span_days": window_days - return_days,
        "acquisition_window": [window_start.isoformat(), acq_end.isoformat()],
        "return_horizon_days": return_days,
        "cohort_size": n,
        "retained": r,
        "d30_rate_pct": round(r / n * 100, 1) if n else None,
        "retained_emails": retained_emails,
    }


def compute_broad_retention(by_user: dict) -> dict:
    """Reuses audience_audit.py's return-rate/multi-day-rate methodology (this
    repo's documented 'truest retention signal') over the FULL set of real,
    non-placeholder users with authoritative history in `by_user` -- not just
    the narrow D30 acquisition-half cohort. Much larger N, so far less
    sensitive to the small-cohort fragility a strict D30 window can have.
    No extra API calls: by_user's per-user history was already pulled live."""
    records = [{"email": e, "convos": [{"created_at": t.isoformat(), "medium": None} for t in times]}
               for e, times in by_user.items()]
    return aa.compute_retention(records)


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
    ap.add_argument("--window-days", type=int, default=60,
                    help="Total lookback. Acquisition span = window-days minus return-days. "
                         "Default 60 (=30d acquisition). Use 90 for a 60d acquisition span -- "
                         "roughly double the cohort at the same D30 definition.")
    ap.add_argument("--return-days", type=int, default=30,
                    help="Return horizon in days (the '30' in D30). Default 30.")
    ap.add_argument("--exclude-email", action="append", default=[], help="Additional placeholder email(s) to exclude (repeatable).")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dump-history", help="Write the resolved {email: [ISO timestamps]} history to this "
                                           "path (PII -- keep local). Lets a follow-up analysis reuse an "
                                           "expensive per-user API pull instead of repeating it.")
    args = ap.parse_args()

    exclude = DEFAULT_EXCLUDE | {e.lower() for e in args.exclude_email}
    key, style = None, None
    if args.api_key or args.account:
        key, style = resolve_key_preferring_applaunch(args)

    if not args.export and not key:
        sys.exit("Provide --export, and/or --account/--api-key.")

    coverage = None
    export_first_ts = None   # earliest activity the export actually covers
    if args.export and key:
        mode = "combo"
        export_by_user, total_threads = load_from_export(args.export, exclude)
        _t = [t for ts in export_by_user.values() for t in ts]
        export_first_ts = min(_t) if _t else None
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
        export_first_ts = min(all_times) if all_times else None
        reference_time = max(all_times) if all_times else datetime.datetime.now(datetime.timezone.utc)
    else:
        mode = "api-only"
        by_user, total_live, total_real = load_from_api_full(key, exclude, style)
        reference_time = datetime.datetime.now(datetime.timezone.utc)

    if args.dump_history:
        json.dump({e: [t.isoformat() for t in times] for e, times in by_user.items()},
                  open(args.dump_history, "w"))
        print(f"history dump -> {args.dump_history} ({len(by_user)} users)", file=sys.stderr)

    # GUARD: widening --window-days past what the export actually covers silently
    # inflates the rate. Candidates come from the export, so anyone first-seen
    # before it is only visible BECAUSE they returned -- a survivor. Measured on
    # one clone: 30.3% for users inside the export vs 87.1% for users before it,
    # same window, same run. Widen the EXPORT, not just the window.
    if args.export and export_first_ts is not None:
        needed_start = reference_time - datetime.timedelta(days=args.window_days)
        if needed_start < export_first_ts:
            short_by = (export_first_ts - needed_start).days
            print(
                f"\n*** WARNING: --window-days {args.window_days} reaches "
                f"{short_by} day(s) BEFORE this export begins "
                f"({export_first_ts.date()}).\n"
                f"    Users first seen in that gap appear only if they came back, so they are\n"
                f"    survivors and will inflate the rate. Either pull an export covering\n"
                f"    >= {args.window_days} days, or drop --window-days back to "
                f"{(reference_time - export_first_ts).days}.\n",
                file=sys.stderr)

    result = compute_d30(by_user, reference_time, args.window_days, args.return_days)
    result["mode"] = mode
    if style:
        result["key_style"] = style
    if coverage:
        result["coverage"] = coverage
    result["top_engaged"] = top_engaged(by_user, args.top)
    result.pop("retained_emails")  # PII -- not for default output
    # Broader retention (return rate / multi-day rate) over ALL real users found
    # active in the window -- not just the narrow D30 acquisition-half cohort.
    # Free: derived from the same authoritative by_user history already pulled.
    result["retention"] = compute_broad_retention(by_user)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("=" * 72)
    style_note = f"  key: {style} ({'App-Launch, high rate limit' if style == 'applaunch' else 'legacy, 120 req/60s cap'})" if style else ""
    print(f"D30 RETENTION  [mode: {mode}]{style_note}")
    print("=" * 72)
    print(f"  Reference time (window end) ... {result['reference_time']}")
    print(f"  Window ......................... {result['window_days']}d lookback = "
          f"{result['acquisition_span_days']}d acquisition + {result['return_days']}d return horizon")
    if coverage:
        print(f"\n  COVERAGE (export vs live audience):")
        print(f"    Live real audience (API) ....... {coverage['live_real_audience']}")
        print(f"    Active in export window ......... {coverage['export_active_users']}")
        print(f"    Coverage ......................... {coverage['coverage_pct']}%")
        print(f"    Registered but silent in export .. {coverage['registered_but_absent_from_export']}")
    print(f"\n  Cohort (first-ever conversation in acquisition span) ... {result['cohort_size']}")
    print(f"  Returned within {result['return_days']} days .............................. {result['retained']}")
    print(f"\n  >>> D{result['return_days']} RETENTION RATE = {result['retained']}/{result['cohort_size']} = {result['d30_rate_pct']}%")
    print(f"      (narrow: only users whose FIRST-EVER visit fell in the "
          f"{result['acquisition_span_days']}-day acquisition span)")

    ret = result["retention"]
    nc = ret["conversers"]
    pct = lambda x: f"{100*x/nc:.1f}%" if nc else "n/a"
    print(f"\n  BROADER RETENTION  (base: ALL {nc} real, non-placeholder users active in this "
          f"{result['window_days']}-day window -- much larger sample than the D30 cohort)")
    print(f"    Multi-day (>=2 distinct days): {ret['multi_day']}/{nc}  ({pct(ret['multi_day'])})   <- truest retention signal")
    print(f"    Return rate (>=2 conversations): {ret['returners_2plus']}/{nc}  ({pct(ret['returners_2plus'])})")
    print(f"    One-and-done: {ret['one_and_done']}  ({pct(ret['one_and_done'])})")
    print(f"    Median conversations/user: {ret['median_per_converser']:.0f}   (mean {ret['mean_per_converser']}, "
          f"max {ret['max_per_user']} -- a high max can skew the mean, median is the honest center)")
    print("    Depth:  " + "  ".join(f"{k}:{v}" for k, v in ret["depth_distribution"].items()))
    print("    Recency (days since last convo):  "
          + "  ".join(f"{k}:{v}" for k, v in ret["recency_days_since_last"].items()))

    print(f"\n  Top {len(result['top_engaged'])} most-engaged users in this data:")
    for row in result["top_engaged"]:
        print(f"    {row['email_masked']:<28} {row['conversations']:>3} convos   last seen {row['last_seen'][:10]}")


if __name__ == "__main__":
    main()
