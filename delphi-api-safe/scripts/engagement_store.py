#!/usr/bin/env python3
"""Durable local engagement store for Delphi conversation exports (READ-ONLY on the API).

WHY
---
Exports are windowed by message date and are handed over one period at a time,
often reusing the same filename. Analysing straight off the raw files means the
numbers only exist as long as the last download survives -- and a re-export can
silently replace the period you already had.

This keeps a small, durable, append-friendly store instead:

    out/store/manifest.json           what has been ingested, from which file
    out/store/<clone>/<YYYY-MM>.jsonl one row per (contact, day)

Each row is the "daily engagement rollup" shape -- deliberately the same shape
we asked Delphi to expose natively, so this can be swapped for a real endpoint
later without touching the analysis:

    {"u": "<contact>", "d": "2026-05-14", "in": 6, "out": 7, "ch": ["embed"]}

Properties that matter:

  * IDEMPOTENT     re-ingesting a month replaces that month cleanly; running the
                   same file twice changes nothing.
  * INCREMENTAL    months are independent files, so adding August never touches
                   May, and a month already present is skipped unless --force.
  * SMALL          a 90 MB export collapses to a few hundred KB, so history can
                   be kept indefinitely and re-analysed without the raw file.
  * AUDITABLE      the manifest records source filename, size, sha256 and row
                   counts, so you can tell what a number was built from.
  * PII-BEARING    contact identifiers are retained (retention needs identity
                   across months) -- the store lives under out/, which is
                   gitignored. Do not commit it.

An export may span several months; rows are filed under the month they belong
to, so a May-to-August export lands as four month files.

Usage:
    # add a period (safe to re-run; already-present months are skipped)
    python3 scripts/engagement_store.py ingest --clone karamo --export may.ndjson

    # replace a month you already have
    python3 scripts/engagement_store.py ingest --clone karamo --export may.ndjson --force

    # what do we hold?
    python3 scripts/engagement_store.py status
    python3 scripts/engagement_store.py status --clone karamo
"""
import argparse, collections, datetime, hashlib, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import d30_retention as d30

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORE = os.path.join(ROOT, "out", "store")
MANIFEST = os.path.join(STORE, "manifest.json")

INBOUND = {"user", "USER"}                 # the human
OUTBOUND = {"agent", "owner", "CLONE"}     # the AI, or the creator broadcasting


# ------------------------------------------------------------------ manifest --

def load_manifest() -> dict:
    if os.path.exists(MANIFEST):
        return json.load(open(MANIFEST))
    return {"version": 1, "clones": {}}


def save_manifest(m: dict):
    os.makedirs(STORE, exist_ok=True)
    json.dump(m, open(MANIFEST, "w"), indent=2, sort_keys=True)


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------- ingest --

def parse_export(path: str, exclude: set):
    """NDJSON -> {(contact, date): {'in':n,'out':n,'ch':set()}} plus a coverage summary."""
    cells = collections.defaultdict(lambda: {"in": 0, "out": 0, "ch": set()})
    threads = skipped = malformed = 0
    seen_days = set()
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            t = json.loads(line)
        except Exception:
            malformed += 1
            continue
        threads += 1
        email = (t.get("user_email") or "").strip()
        if not email or not d30.is_real(email, exclude):
            skipped += 1
            continue
        ch = t.get("medium") or "unknown"
        for m in t.get("messages", []):
            ts = d30.parse_ts(m.get("created_at") or "")
            if not ts:
                continue
            day = ts.date()
            seen_days.add(day)
            cell = cells[(email.lower(), day.isoformat())]
            s = m.get("sender")
            if s in INBOUND:
                cell["in"] += 1
            elif s in OUTBOUND:
                cell["out"] += 1
            cell["ch"].add(ch)
    return cells, {
        "threads": threads,
        "threads_skipped_placeholder_or_fake": skipped,
        "malformed_lines": malformed,
        "first_day": min(seen_days).isoformat() if seen_days else None,
        "last_day": max(seen_days).isoformat() if seen_days else None,
        "active_days": len(seen_days),
    }


def ingest(clone: str, export: str, force: bool, exclude: set) -> int:
    if not os.path.exists(export):
        sys.exit(f"No such export: {export}")
    man = load_manifest()
    entry = man["clones"].setdefault(clone, {"months": {}})

    digest = sha256(export)
    already = [mo for mo, meta in entry["months"].items() if meta.get("sha256") == digest]
    if already and not force:
        print(f"  {clone}: this exact file is already ingested as {sorted(already)} — skipping "
              f"(use --force to re-ingest)")
        return 0

    cells, cov = parse_export(export, exclude)
    if not cells:
        print(f"  {clone}: no real-contact activity found in {os.path.basename(export)}")
        return 0

    by_month = collections.defaultdict(list)
    for (u, d), c in cells.items():
        by_month[d[:7]].append({"u": u, "d": d, "in": c["in"], "out": c["out"],
                                "ch": sorted(c["ch"])})

    os.makedirs(os.path.join(STORE, clone), exist_ok=True)
    written = 0
    for month, rows in sorted(by_month.items()):
        path = os.path.join(STORE, clone, f"{month}.jsonl")
        if os.path.exists(path) and not force:
            print(f"  {clone} {month}: already stored ({sum(1 for _ in open(path))} rows) — "
                  f"skipping (use --force to replace)")
            continue
        rows.sort(key=lambda r: (r["d"], r["u"]))
        with open(path, "w") as f:
            for r in rows:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        contacts = len({r["u"] for r in rows})
        inb = sum(r["in"] for r in rows)
        entry["months"][month] = {
            "rows": len(rows), "contacts": contacts, "inbound_messages": inb,
            "outbound_messages": sum(r["out"] for r in rows),
            "source_file": os.path.basename(export),
            "source_bytes": os.path.getsize(export),
            "sha256": digest,
            "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "export_coverage": cov,
        }
        print(f"  {clone} {month}: {len(rows)} rows · {contacts} contacts · {inb} inbound msgs")
        written += 1

    save_manifest(man)
    return written


# ------------------------------------------------------------------- status --

def status(clone_filter):
    man = load_manifest()
    if not man["clones"]:
        print("store is empty"); return
    print(f"{'clone':<20} {'month':<9} {'contacts':>9} {'inbound':>9} {'rows':>8}  source")
    print("-" * 88)
    for clone in sorted(man["clones"]):
        if clone_filter and clone != clone_filter:
            continue
        for month in sorted(man["clones"][clone]["months"]):
            m = man["clones"][clone]["months"][month]
            print(f"{clone:<20} {month:<9} {m['contacts']:>9} {m['inbound_messages']:>9} "
                  f"{m['rows']:>8}  {m['source_file'][:34]}")
    print()
    months = sorted({mo for c in man["clones"].values() for mo in c["months"]})
    print(f"clones: {len(man['clones'])}   months held: {', '.join(months) if months else '-'}")


# --------------------------------------------------------------------- read --

def load(clone: str, months=None) -> dict:
    """Store -> {contact: {date: {'in':n,'out':n,'ch':[...]}}}, all months merged."""
    out = collections.defaultdict(dict)
    d = os.path.join(STORE, clone)
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".jsonl"):
            continue
        if months and fn[:-6] not in months:
            continue
        for line in open(os.path.join(d, fn)):
            r = json.loads(line)
            # union across months is idempotent -- a duplicated day just overwrites
            out[r["u"]][r["d"]] = {"in": r["in"], "out": r["out"], "ch": r.get("ch", [])}
    return out


def main():
    ap = argparse.ArgumentParser(description="Durable engagement store for Delphi exports.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("ingest", help="Add an export to the store.")
    i.add_argument("--clone", required=True, help="Clone slug, e.g. karamo.")
    i.add_argument("--export", required=True)
    i.add_argument("--force", action="store_true", help="Replace months already stored.")
    i.add_argument("--exclude-email", action="append", default=[])

    s = sub.add_parser("status", help="Show what the store holds.")
    s.add_argument("--clone")

    args = ap.parse_args()
    if args.cmd == "ingest":
        exclude = d30.DEFAULT_EXCLUDE | {e.lower() for e in args.exclude_email}
        ingest(args.clone, args.export, args.force, exclude)
    else:
        status(args.clone)


if __name__ == "__main__":
    main()
