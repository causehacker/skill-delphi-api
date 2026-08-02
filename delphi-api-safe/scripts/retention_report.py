#!/usr/bin/env python3
"""Retention across every month held in the engagement store (READ-ONLY, no API).

Reads out/store (see engagement_store.py) rather than raw exports, so the
numbers survive the originals and new months can be added without re-deriving
old ones.

THREE MEASURES, ALL INBOUND-ONLY
--------------------------------
Only messages a human actually sent count (`in > 0`). AI replies and creator
broadcasts are excluded — on some accounts outbound outnumbers inbound 15:1, so
counting either would mostly measure how much the creator sends.

  reply rate      of contacts present, how many ever sent anything.
                  On pull channels (web/embed) the visitor starts the
                  conversation so this is ~100% by construction; on push
                  channels (SMS blasts) it is the real funnel number. Read it
                  against the channel, never across channels.

  30-day return   of people whose FIRST inbound day is at least 30 days before
                  the data ends, how many sent again on a DIFFERENT day within
                  30. Anyone who arrived too recently is EXCLUDED, not counted
                  as churned — so every person counted was genuinely observed
                  for a full 30 days.

  multi-day       of people who ever sent anything, how many sent on >=2
                  distinct days at any point. A corroborating measure: it uses
                  the whole window rather than a fixed horizon, so when the two
                  agree the signal is the audience and not the definition.

A "return" always requires a DIFFERENT calendar day. Several messages in one
sitting are one visit; a message the next day is a decision to come back.

MONTH-OVER-MONTH
----------------
For consecutive months A→B: of the people who sent something in A, how many
sent something in B. Cohorts are compared only at matched elapsed horizons
elsewhere; this one is naturally matched because both months are complete.
A partial trailing month is flagged rather than shown as a decline.

Usage:
    python3 scripts/retention_report.py
    python3 scripts/retention_report.py --clone karamo --json
    python3 scripts/retention_report.py --months 2026-06,2026-07
"""
import argparse, collections, datetime, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engagement_store as es

D = datetime.timedelta


def inbound_days(clone, months=None):
    """{contact: sorted[date]} using only days the human sent something."""
    data = es.load(clone, months)
    out = {}
    for u, days in data.items():
        ds = sorted(datetime.date.fromisoformat(d) for d, c in days.items() if c["in"] > 0)
        if ds:
            out[u] = ds
    return out, data


def analyse(clone, months=None):
    days, raw = inbound_days(clone, months)
    if not days:
        return None
    reached = len(raw)
    engaged = len(days)
    end = max(v[-1] for v in days.values())
    start = min(v[0] for v in days.values())
    cutoff = end - D(days=30)

    cohort = ret = 0
    for v in days.values():
        first = v[0]
        if first > cutoff:
            continue
        cohort += 1
        if any(x != first and x <= first + D(days=30) for x in v[1:]):
            ret += 1

    multi = sum(1 for v in days.values() if len(v) >= 2)

    # month-over-month: who sent in month A and again in month B
    by_month = collections.defaultdict(set)
    for u, v in days.items():
        for d in v:
            by_month[f"{d.year}-{d.month:02d}"].add(u)
    mlist = sorted(by_month)
    steps = []
    for a, b in zip(mlist, mlist[1:]):
        A, B = by_month[a], by_month[b]
        steps.append({"from": a, "to": b, "engaged_from": len(A), "engaged_to": len(B),
                      "returned": len(A & B),
                      "rate_pct": round(len(A & B) / len(A) * 100, 1) if A else None})

    inb = sum(c["in"] for v in raw.values() for c in v.values())
    outb = sum(c["out"] for v in raw.values() for c in v.values())
    chan = collections.Counter()
    for u in days:
        cs = collections.Counter()
        for c in raw[u].values():
            for x in c.get("ch", []):
                cs[x] += 1
        if cs:
            chan[cs.most_common(1)[0][0]] += 1

    return {
        "clone": clone,
        "months": mlist,
        "data_start": start.isoformat(), "data_end": end.isoformat(),
        "reached": reached, "engaged": engaged,
        "reply_rate_pct": round(engaged / reached * 100, 1) if reached else None,
        "cohort_30d": cohort, "returned_30d": ret,
        "return_30d_pct": round(ret / cohort * 100, 1) if cohort else None,
        "observable_pct": round(cohort / engaged * 100, 1) if engaged else None,
        "multi_day": multi,
        "multi_day_pct": round(multi / engaged * 100, 1) if engaged else None,
        "inbound_messages": inb, "outbound_messages": outb,
        "outbound_ratio": round(outb / inb, 1) if inb else None,
        "monthly_steps": steps,
        "engaged_by_month": {m: len(s) for m, s in sorted(by_month.items())},
        "dominant_channel": chan.most_common(1)[0][0] if chan else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Retention across the engagement store.")
    ap.add_argument("--clone")
    ap.add_argument("--months", help="Comma-separated YYYY-MM to restrict to.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    months = set(args.months.split(",")) if args.months else None

    clones = [args.clone] if args.clone else sorted(
        d for d in os.listdir(es.STORE) if os.path.isdir(os.path.join(es.STORE, d)))
    results = [r for r in (analyse(c, months) for c in clones) if r]
    if not results:
        sys.exit("Nothing in the store for that selection.")

    if args.json:
        print(json.dumps(results, indent=2)); return

    results.sort(key=lambda r: -(r["return_30d_pct"] or 0))
    print("=" * 108)
    print("RETENTION — inbound messages only (AI replies and creator broadcasts excluded)")
    print("=" * 108)
    print(f"  {'clone':<18} {'months':<26} {'engaged':>8} {'30d return':>12} {'multi-day':>11} "
          f"{'obs':>5} {'out:in':>7}")
    print("  " + "-" * 104)
    for r in results:
        span = f"{r['months'][0]}→{r['months'][-1]}" if len(r["months"]) > 1 else r["months"][0]
        span = f"{span} ({len(r['months'])}mo)"
        ret = f"{r['return_30d_pct']}% ({r['returned_30d']}/{r['cohort_30d']})"
        md = f"{r['multi_day_pct']}%"
        print(f"  {r['clone']:<18} {span:<26} {r['engaged']:>8} {ret:>12} {md:>11} "
              f"{str(r['observable_pct'])+'%':>5} {str(r['outbound_ratio'])+'x':>7}")

    print(f"\n  MONTH OVER MONTH — of people who sent in month A, how many sent again in month B")
    for r in results:
        if not r["monthly_steps"]:
            continue
        parts = [f"{s['from'][-2:]}→{s['to'][-2:]} {s['rate_pct']}% ({s['returned']}/{s['engaged_from']})"
                 for s in r["monthly_steps"]]
        counts = " · ".join(f"{m[-2:]}:{n}" for m, n in r["engaged_by_month"].items())
        print(f"    {r['clone']:<18} {'   '.join(parts)}")
        print(f"    {'':<18} engaged by month — {counts}")

    print(f"\n  reply rate (read against channel — ~100% is definitional on web/embed)")
    for r in results:
        print(f"    {r['clone']:<18} {str(r['reply_rate_pct'])+'%':>7} of {r['reached']:>6} reached"
              f"   [{r['dominant_channel']}]")


if __name__ == "__main__":
    main()
