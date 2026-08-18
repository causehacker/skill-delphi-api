#!/usr/bin/env bash
# One-command retention pipeline: validate -> ingest -> report.
#
#   ./delphi-api-safe/scripts/run_retention.sh ~/Downloads/*.ndjson
#   ./delphi-api-safe/scripts/run_retention.sh --force ~/Downloads/*.ndjson   # re-ingest even if held
#   ./delphi-api-safe/scripts/run_retention.sh --dry-run ~/Downloads/*.ndjson # validate only
#
# The clone slug is taken from the filename: "<slug>-conversations-*.ndjson".
# Files that fail validation are reported and skipped, never ingested.
# Safe to re-run: the store is idempotent per (clone, month).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
FORCE=""; DRY=0; FILES=()
for a in "$@"; do
  case "$a" in
    --force)   FORCE="--force" ;;
    --dry-run) DRY=1 ;;
    *)         FILES+=("$a") ;;
  esac
done
[ ${#FILES[@]} -gt 0 ] || { echo "usage: $0 [--force] [--dry-run] <export.ndjson>..."; exit 2; }

echo "== 1/3  validate =="
OK=(); BAD=0
for f in "${FILES[@]}"; do
  base="$(basename "$f")"
  slug="${base%%-conversations-*}"
  if [ "$slug" = "$base" ]; then echo "  SKIP  $base  (filename must be <slug>-conversations-*.ndjson)"; BAD=$((BAD+1)); continue; fi
  if python3 - "$f" <<'PY'
import sys, json, datetime, collections
p=sys.argv[1]; lines=bad=0; days=set(); handles=collections.Counter(); lo=hi=None
for line in open(p):
    line=line.strip()
    if not line: continue
    lines+=1
    try: t=json.loads(line)
    except Exception: bad+=1; continue
    handles[t.get("handle")]+=1
    for m in t.get("messages",[]):
        s=(m.get("created_at") or "").replace("Z","+00:00")
        try: d=datetime.datetime.fromisoformat(s).date()
        except Exception: continue
        days.add(d); lo=d if lo is None or d<lo else lo; hi=d if hi is None or d>hi else hi
if bad or not days or len(handles)>1:
    print(f"  FAIL  {p.split('/')[-1]}: malformed={bad} handles={dict(handles)} days={len(days)}"); sys.exit(1)
span=(hi-lo).days+1; gaps=span-len(days)
flag="" if gaps==0 else f"  ({gaps} gap day(s))"
print(f"  ok    {p.split('/')[-1]:<50} {lo} -> {hi}  {lines} lines{flag}")
PY
  then OK+=("$f"); else BAD=$((BAD+1)); fi
done
echo "  passed ${#OK[@]}, failed $BAD"
[ ${#OK[@]} -gt 0 ] || { echo "nothing to ingest"; exit 1; }
[ $DRY -eq 1 ] && { echo "(dry run, stopping here)"; exit 0; }

echo ""
echo "== 2/3  ingest =="
for f in "${OK[@]}"; do
  base="$(basename "$f")"; slug="${base%%-conversations-*}"
  python3 "$HERE/engagement_store.py" ingest --clone "$slug" --export "$f" $FORCE
done

echo ""
echo "== 3/3  report =="
python3 "$HERE/engagement_store.py" status
echo ""
python3 "$HERE/retention_report.py"
