#!/usr/bin/env python3
"""Inbound-only engagement from a Delphi NDJSON export (READ-ONLY, no API calls).

WHY THIS EXISTS
---------------
Conversation-count retention breaks on broadcast channels. Two problems:

1. **Conversation records are chunked differently per channel.** A web visitor
   creates a new conversation per session, so "conversations" ~ "visits". An
   SMS/WhatsApp contact has one long-lived thread that just gets appended to, so
   the same person shows 2-3 "conversations" lifetime while exchanging hundreds
   of messages. Counting conversations measures how the platform slices threads,
   not whether a human came back.

2. **Most messages are outbound.** Exports carry `sender` in {user, agent,
   owner}: `agent` is the AI replying, `owner` is the creator broadcasting, and
   only `user` is the actual person. On a broadcast-heavy clone the outbound
   messages dwarf inbound, so any "message activity" metric mostly measures the
   creator's own send volume.

So this script counts only what a human actually sent, and asks: on how many
DISTINCT DAYS did this person send at least one message? That question means the
same thing on SMS, WhatsApp, web, and embed.

    reached   = people present in the export at all (may be broadcast-only)
    responded = people who sent >=1 inbound message ever
    multi-day = people who sent messages on >=2 distinct days   <- engagement
    reply rate = responded / reached

Everything is scoped to the export window; no API calls are made.

Usage:
    python3 scripts/inbound_engagement.py --export conv.ndjson
    python3 scripts/inbound_engagement.py --export conv.ndjson --label "Lewis Howes" --json
"""
import argparse, collections, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audience_audit as aa
import d30_retention as d30

INBOUND = {"user"}          # the human. 'agent' = AI, 'owner' = creator broadcasting
LEGACY_INBOUND = {"USER"}   # older exports used CLONE/USER


def main():
    ap = argparse.ArgumentParser(description="Inbound-only engagement from an NDJSON export.")
    ap.add_argument("--export", required=True)
    ap.add_argument("--label", default="")
    ap.add_argument("--exclude-email", action="append", default=[])
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    exclude = d30.DEFAULT_EXCLUDE | {e.lower() for e in args.exclude_email}

    reached = set()
    inbound_days = collections.defaultdict(set)   # email -> {date}
    inbound_msgs = collections.Counter()
    sender_counts = collections.Counter()
    medium_counts = collections.Counter()
    medium_by_user = collections.defaultdict(collections.Counter)
    threads = 0

    for line in open(args.export):
        line = line.strip()
        if not line:
            continue
        t = json.loads(line)
        email = (t.get("user_email") or "").strip()
        if not email or not d30.is_real(email, exclude):
            continue
        threads += 1
        reached.add(email)
        med = t.get("medium") or "unknown"
        medium_counts[med] += 1
        medium_by_user[email][med] += 1
        for m in t.get("messages", []):
            s = m.get("sender")
            sender_counts[s] += 1
            if s in INBOUND or s in LEGACY_INBOUND:
                ts = d30.parse_ts(m.get("created_at") or "")
                if ts:
                    inbound_days[email].add(ts.date())
                    inbound_msgs[email] += 1

    responded = {e for e, d in inbound_days.items() if d}
    multi = {e for e, d in inbound_days.items() if len(d) >= 2}
    three_plus = {e for e, d in inbound_days.items() if len(d) >= 3}

    dist = collections.Counter()
    for e in reached:
        n = len(inbound_days.get(e, ()))
        dist[0 if n == 0 else 1 if n == 1 else 2 if n <= 3 else 3 if n <= 7 else 4] += 1

    # channel mix by the user's dominant medium
    dom = collections.Counter()
    for e in reached:
        c = medium_by_user[e]
        dom[c.most_common(1)[0][0] if c else "unknown"] += 1

    out = {
        "label": args.label or os.path.basename(args.export),
        "threads": threads,
        "reached_users": len(reached),
        "responded_users": len(responded),
        "reply_rate_pct": round(len(responded) / len(reached) * 100, 1) if reached else None,
        "multi_day_users": len(multi),
        # of everyone reached
        "multi_day_of_reached_pct": round(len(multi) / len(reached) * 100, 1) if reached else None,
        # of those who ever replied -- the fair "did engaged people come back" number
        "multi_day_of_responders_pct": round(len(multi) / len(responded) * 100, 1) if responded else None,
        "three_plus_day_users": len(three_plus),
        "inbound_messages": sum(inbound_msgs.values()),
        "sender_mix": dict(sender_counts),
        "medium_mix": dict(medium_counts),
        "dominant_medium_by_user": dict(dom),
        "inbound_day_distribution": {"0": dist[0], "1": dist[1], "2-3": dist[2],
                                     "4-7": dist[3], "8+": dist[4]},
    }

    if args.json:
        print(json.dumps(out, indent=2))
        return

    print("=" * 72)
    print(f"INBOUND ENGAGEMENT — {out['label']}")
    print("=" * 72)
    print(f"  threads: {threads}   reached users: {out['reached_users']}")
    print(f"  sender mix: {out['sender_mix']}")
    print(f"  medium mix: {out['medium_mix']}")
    print()
    print(f"  Replied at least once .......... {out['responded_users']} "
          f"({out['reply_rate_pct']}% of reached)")
    print(f"  Sent on >=2 distinct days ...... {out['multi_day_users']} "
          f"({out['multi_day_of_reached_pct']}% of reached | "
          f"{out['multi_day_of_responders_pct']}% of responders)")
    print(f"  Sent on >=3 distinct days ...... {out['three_plus_day_users']}")
    print(f"  inbound messages total ......... {out['inbound_messages']}")
    print(f"  inbound days per user: " +
          "  ".join(f"{k}:{v}" for k, v in out["inbound_day_distribution"].items()))


if __name__ == "__main__":
    main()
