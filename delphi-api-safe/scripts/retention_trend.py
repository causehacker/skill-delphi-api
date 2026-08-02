#!/usr/bin/env python3
"""Month-over-month retention trend for a Delphi clone (READ-ONLY).

Answers "is retention improving or getting worse?" rather than just "what is it
right now" -- by splitting the audience into monthly acquisition cohorts and
measuring each one at matched elapsed horizons.

THE COMPARABILITY PROBLEM THIS SOLVES
--------------------------------------
You cannot compare "June's D30" to "July's D30" on 2 Aug: a user who first
showed up on 31 Jul has not had 30 days to come back yet, so July's D30 would
be artificially low purely because time hasn't passed. That looks like a
regression when nothing changed.

Fix: for each horizon H (1/7/14/30 days), only count users whose H-day window
has actually closed -- i.e. first_seen <= reference - H. Every cohort is then
measured over the same amount of elapsed opportunity, so June-at-7-days vs
July-at-7-days is a fair comparison. Horizons with too few eligible users are
reported as None rather than a misleading number.

COHORT DEFINITION AND ITS ONE BIAS
-----------------------------------
A user belongs to month M if their FIRST EVER conversation was in M (from full
API history, not just the export window).

Cohorts INSIDE the export window are unbiased: to be first-seen in June you must
have had June activity, and all June activity is in a Jun-Aug export, so every
June-cohort member is captured.

Cohorts BEFORE the window are survivor-biased and are flagged as such: a user
who first appeared in April and churned in April never shows up in a Jun-Aug
export, so April's cohort only contains people who survived to be seen again.
Their retention will look far too good. Reported, but marked UNRELIABLE.

Usage:
    # reuse an existing history dump (no API calls -- preferred)
    python3 scripts/retention_trend.py --history out/lewis_howes_history.json

    # or resolve history live, same sources as d30_retention.py
    python3 scripts/retention_trend.py --export conv.ndjson --account lewis_howes

    python3 scripts/retention_trend.py --history out/x.json --window-start 2026-06-01 --json
"""
import argparse, datetime, json, os, sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audience_audit as aa
import d30_retention as d30

HORIZONS = [1, 7, 14, 30]
MIN_COHORT = 20   # below this, a rate is too noisy to publish


def month_key(dt):
    return f"{dt.year:04d}-{dt.month:02d}"


def month_bounds(key):
    y, m = (int(x) for x in key.split("-"))
    start = datetime.datetime(y, m, 1, tzinfo=datetime.timezone.utc)
    end = (datetime.datetime(y + (m == 12), (m % 12) + 1, 1, tzinfo=datetime.timezone.utc))
    return start, end


def load_history(path):
    raw = json.load(open(path))
    out = {}
    for e, times in raw.items():
        ts = sorted(d30.parse_ts(t) for t in times if d30.parse_ts(t))
        if ts:
            out[e] = ts
    return out


def monthly_cohorts(by_user, reference, window_start):
    """Per-month acquisition cohorts measured at matched elapsed horizons."""
    cohorts = {}
    for email, times in by_user.items():
        first = times[0]
        cohorts.setdefault(month_key(first), []).append((email, times))

    rows = []
    for key in sorted(cohorts):
        members = cohorts[key]
        m_start, m_end = month_bounds(key)
        # Unbiased only if the whole month sits inside the observation window:
        # otherwise we only see users who survived long enough to reappear.
        reliable = window_start is None or m_start >= window_start

        row = {
            "month": key,
            "cohort_size": len(members),
            "reliable": reliable,
            "note": "" if reliable else "survivor-biased: month predates the export window",
            "horizons": {},
        }
        for h in HORIZONS:
            cutoff = reference - datetime.timedelta(days=h)
            eligible = [(e, t) for e, t in members if t[0] <= cutoff]
            if len(eligible) < MIN_COHORT:
                row["horizons"][f"d{h}"] = {
                    "eligible": len(eligible), "returned": None, "rate_pct": None,
                    "note": f"only {len(eligible)} users have had {h} full days -- too few to report",
                }
                continue
            ret = 0
            for e, t in eligible:
                lim = t[0] + datetime.timedelta(days=h)
                if any(t[0] < x <= lim for x in t[1:]):
                    ret += 1
            row["horizons"][f"d{h}"] = {
                "eligible": len(eligible), "returned": ret,
                "rate_pct": round(ret / len(eligible) * 100, 1), "note": "",
            }
        rows.append(row)
    return rows


def monthly_activity(by_user, window_start, reference):
    """Who was active each month, split new vs returning, plus in-month multi-day."""
    months = {}
    for email, times in by_user.items():
        first = times[0]
        seen_months = {}
        for t in times:
            seen_months.setdefault(month_key(t), []).append(t)
        for mk, ts in seen_months.items():
            b = months.setdefault(mk, {"active": 0, "new": 0, "returning": 0,
                                       "conversations": 0, "multi_day": 0})
            b["active"] += 1
            b["conversations"] += len(ts)
            if month_key(first) == mk:
                b["new"] += 1
            else:
                b["returning"] += 1
            if len({t.date() for t in ts}) >= 2:
                b["multi_day"] += 1

    out = []
    for mk in sorted(months):
        m_start, m_end = month_bounds(mk)
        if window_start is not None and m_end <= window_start:
            continue  # entirely before the observation window -- not meaningful
        b = months[mk]
        partial = m_end > reference
        out.append({
            "month": mk,
            "partial_month": partial,
            "active_users": b["active"],
            "new_users": b["new"],
            "returning_users": b["returning"],
            "conversations": b["conversations"],
            "multi_day_users": b["multi_day"],
            "multi_day_rate_pct": round(b["multi_day"] / b["active"] * 100, 1) if b["active"] else None,
            "returning_share_pct": round(b["returning"] / b["active"] * 100, 1) if b["active"] else None,
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Month-over-month retention trend (read-only).")
    ap.add_argument("--history", help="Reuse a {email:[iso]} dump from d30_retention.py --dump-history.")
    ap.add_argument("--export", help="NDJSON export (used with --account, or alone).")
    ap.add_argument("--account")
    ap.add_argument("--api-key")
    ap.add_argument("--window-start", help="ISO date the observation window opens (e.g. 2026-06-01). "
                                           "Cohorts before this are flagged survivor-biased. "
                                           "Inferred from the export when omitted.")
    ap.add_argument("--exclude-email", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dump-history", help="Write resolved {email:[iso]} history here (PII -- keep local).")
    args = ap.parse_args()

    exclude = d30.DEFAULT_EXCLUDE | {e.lower() for e in args.exclude_email}
    reference = datetime.datetime.now(datetime.timezone.utc)

    if args.history:
        by_user = load_history(args.history)
        by_user = {e: t for e, t in by_user.items() if d30.is_real(e, exclude)}
        source = f"history dump ({args.history})"
    elif args.export and (args.account or args.api_key):
        key, style = d30.resolve_key_preferring_applaunch(args)
        export_by_user, _ = d30.load_from_export(args.export, exclude)
        by_user = d30.load_api_for_emails(list(export_by_user.keys()), key, style)
        source = "export + live API"
    elif args.export:
        by_user, _ = d30.load_from_export(args.export, exclude)
        source = "export only (first-seen = first in export, not first ever)"
    else:
        sys.exit("Provide --history, or --export (optionally with --account/--api-key).")

    if not by_user:
        sys.exit("No users resolved.")

    if args.dump_history:
        json.dump({e: [t.isoformat() for t in times] for e, times in by_user.items()},
                  open(args.dump_history, "w"))
        print(f"history dump -> {args.dump_history} ({len(by_user)} users)", file=sys.stderr)

    window_start = None
    if args.window_start:
        window_start = datetime.datetime.fromisoformat(args.window_start).replace(
            tzinfo=datetime.timezone.utc)
    elif args.export:
        allt = [t for ts in by_user.values() for t in ts]
        window_start = min(allt) if allt else None

    cohorts = monthly_cohorts(by_user, reference, window_start)
    activity = monthly_activity(by_user, window_start, reference)
    out = {
        "source": source,
        "reference_time": reference.isoformat(),
        "window_start": window_start.isoformat() if window_start else None,
        "users_analyzed": len(by_user),
        "monthly_cohorts": cohorts,
        "monthly_activity": activity,
    }

    if args.json:
        print(json.dumps(out, indent=2))
        return

    print("=" * 78)
    print("RETENTION TREND — monthly acquisition cohorts at matched horizons")
    print("=" * 78)
    print(f"  source: {source}")
    print(f"  users analyzed: {len(by_user)}")
    print(f"  reference: {reference.isoformat()}")
    if window_start:
        print(f"  observation window opens: {window_start.date()}")

    print(f"\n  COHORT RETURN RATES (each horizon counts only users whose window has closed)")
    hdr = f"    {'cohort':<10} {'size':>6}   " + "  ".join(f"{'d'+str(h):>13}" for h in HORIZONS)
    print(hdr); print("    " + "-" * (len(hdr) - 4))
    for r in cohorts:
        cells = []
        for h in HORIZONS:
            c = r["horizons"][f"d{h}"]
            cells.append(f"{c['rate_pct']:>5}% ({c['eligible']:>4})" if c["rate_pct"] is not None
                         else f"{'--':>13}")
        flag = "" if r["reliable"] else "  <- UNRELIABLE (survivor-biased)"
        print(f"    {r['month']:<10} {r['cohort_size']:>6}   " + "  ".join(cells) + flag)
    print(f"\n    (percent = share who had another conversation within that many days of their")
    print(f"     first; number in parens = users eligible, i.e. window fully elapsed.")
    print(f"     '--' = fewer than {MIN_COHORT} eligible users, too noisy to report.)")

    print(f"\n  MONTHLY ACTIVITY")
    hdr2 = (f"    {'month':<10} {'active':>7} {'new':>7} {'returning':>10} "
            f"{'ret.share':>10} {'convos':>8} {'multi-day':>10}")
    print(hdr2); print("    " + "-" * (len(hdr2) - 4))
    for a in activity:
        mark = " *" if a["partial_month"] else ""
        print(f"    {a['month']:<10} {a['active_users']:>7} {a['new_users']:>7} "
              f"{a['returning_users']:>10} {str(a['returning_share_pct'])+'%':>10} "
              f"{a['conversations']:>8} {str(a['multi_day_rate_pct'])+'%':>10}{mark}")
    if any(a["partial_month"] for a in activity):
        print("    * partial month — not yet complete, do not read as a decline")


if __name__ == "__main__":
    main()
