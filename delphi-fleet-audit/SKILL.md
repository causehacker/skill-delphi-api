---
name: delphi-fleet-audit
description: Sweep every Delphi account in keys.json in one pass — health check (clone/conversation/stream) and optional audience sizing per clone — and produce a single cross-account matrix. Use when the user says "test all my accounts", "check the whole fleet", "run a sweep", "which clones are down", "audience sizes across all accounts", or asks to compare clones. Also use for scheduled/recurring fleet health checks.
---

# Delphi Fleet Audit

One command, every clone. Jim runs multiple production Delphi accounts; checking
them one key at a time wastes an hour that this skill spends in minutes. The
deliverable is always **one matrix, all accounts, keys redacted**.

## Key registry

`keys.json` (repo root, gitignored) is the sanctioned multi-account registry:

```json
{ "accounts": { "karamo": "dsk-...", "drramani": "dsk-..." } }
```

Never ask the user to paste every key if `keys.json` exists — read it. Never
create or edit `keys.json` yourself; if it's missing, ask the user to create it
(show the format above) or to paste keys for this session only.

## Workflow

1. **Run the sweep** (read-only; creates only throwaway conversations):

```bash
# Health check across all accounts in keys.json:
python3 delphi-fleet-audit/scripts/fleet_audit.py

# Health + audience sizing (total/real/filtered per clone — slower):
python3 delphi-fleet-audit/scripts/fleet_audit.py --sizing

# Subset of accounts, machine-readable:
python3 delphi-fleet-audit/scripts/fleet_audit.py --accounts karamo,drramani --json

# Explicit keys (no keys.json), e.g. keys pasted this session:
python3 delphi-fleet-audit/scripts/fleet_audit.py --keys "dsk-aaa,dsk-bbb"
```

2. **Present the matrix** exactly like the skill's house table:

| Account | Key | Clone | Conversation | Stream | Overall | Note |
|---------|-----|-------|--------------|--------|---------|------|
| karamo | `dsk-****abcd` | Karamo | PASS | PASS | **PASS** | |
| drramani | `dsk-****wxyz` | — | FAIL (403) | — | **FAIL** | key not active |

With `--sizing`, add `Total / Real / Filtered` columns — always all three
numbers, never the raw total alone.

3. **Interpret in plain English**, one line per non-PASS row: "drramani's key is
   returning 403 everywhere — the key is inactive, not a code problem."
4. **Escalate per-clone failures** to the `delphi-incident-report` skill (a
   stream 500 on one clone while others pass is a per-clone incident).

## Rules

- **Pace hard.** Rate limits are per key, but a fleet sweep multiplies calls:
  the script sleeps between accounts and between paginated sizing calls; do not
  add parallelism.
- A clone failing `stream` while others pass = per-clone incident. All clones
  failing the same way = suspect the API or the network, not the keys.
- Deep retention analytics stay in `audience_audit.py` (per-account) — this
  skill sizes audiences but does not pull per-user conversations for a whole
  fleet in one shot without the user acknowledging the runtime (minutes per
  clone with a large audience).
- Full JSON output with emails/PII goes to `out/` only. The chat reply carries
  the matrix and counts, redacted.

## Comparing runs

`--json --out out/fleet-<date>.json` saves a snapshot. When the user asks
"what changed since last week", diff the two snapshots' `overall` and
`real_users` fields per account and report only the deltas.
