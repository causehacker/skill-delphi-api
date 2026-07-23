---
name: delphi-docs-sync
description: Sync this repo's Delphi V3 API coverage with the latest official docs and fan new/changed endpoints out across every surface (references, SKILL.md, test script, playground, evals, README, HOW-TO). Use when the user says "pull latest from the API docs", "is anything new in the Delphi docs", "add this endpoint" (with pasted docs), "update the skill for <endpoint>", or pastes a docs.delphi.ai page or URL. Also use to check integration completeness: "did we cover everything", "run the coverage check", "what surfaces are missing".
---

# Delphi Docs Sync

Turn a Delphi docs page (pasted, fetched via MCP, or described) into a **complete**
integration across every surface of this repo, and verify parity with a
deterministic coverage check. An endpoint integrated on one surface but missing
from another is a bug — this skill exists to make that impossible.

## Step 1 — Get the docs content

In order of preference:

1. **`delphi-help-center` MCP server** (GitBook) if connected this session — query it for the page.
2. **User-pasted content** — Jim will paste a docs page on request; ask once, clearly.
3. Do **not** loop on `WebFetch`/`curl` against docs.delphi.ai — it 403s unauthenticated agents (the `.md` suffix does not help). One attempt maximum, then fall back to 1 or 2.

Never guess request/response shapes. If the docs are unavailable and the user
can't paste them, stop and say exactly which endpoint fields are unknown.

## Step 2 — Diff against current coverage

Run the coverage check to see what this repo already knows:

```bash
python3 delphi-docs-sync/scripts/coverage_check.py
```

It parses every surface and prints a matrix of `METHOD /v3/path` × surface
(references / skill / tests / playground). Compare the docs content against the
matrix and produce a short gap list:

- **New endpoint** — in docs, not in repo
- **Changed endpoint** — field/behavior difference between docs and `references/v3-endpoints.md`
- **Repo-only endpoint** — in repo, not (or no longer) in docs: flag it, do not delete anything without asking
- **Partial integration** — endpoint exists but is missing from one or more surfaces

Report the gap list to the user in one short table before making changes.

## Step 3 — Fan out each new/changed endpoint

For each endpoint, update **all** of these (this is the Fan-Out Rule from CLAUDE.md):

1. `delphi-api-safe/references/v3-endpoints.md` — method, path, body/query fields with types and required flags, response shape, quirks. Mark anything you haven't verified against the live API as *(untested — from docs)*.
2. `delphi-api-safe/SKILL.md` — endpoint list entry; plus a curl example under "Standard commands" if user-facing. Update the frontmatter `description` if this adds a new trigger-worthy capability.
3. `delphi-api-safe/scripts/test_delphi_v3.py` — a `test_*` function (house shape: `"<name>": "PASS"|"FAIL"`, `"<name>_http"`, `"note"`, previews ≤280 chars), wired into `main()`, plus a `*_summary` block.
4. `docs/api-reference.html` — an `ENDPOINTS` array card (data only: `body`/`query`/`extra`/`bodyFn`/`queryFn`/`pathFn`). Bump the endpoint count in the page subtitle **and** in `README.md`.
5. `delphi-api-safe/evals/evals.json` — ≥1 natural-language eval, next sequential id, placeholder key in `dsk-fakeStyle123` form.
6. `README.md` + `docs/HOW-TO.md` — coverage lists and examples.
7. If a new CLI flag is warranted: `scripts/run_smoke.py`, `scripts/setup.py`, `smoke-config.example.json`, `Makefile`.

Tier-gated endpoints (e.g. `/v3/search/*` = Immortal-only) must say so in every
surface where a user could hit the gate.

## Step 4 — Verify

```bash
python3 -c "import ast; ast.parse(open('delphi-api-safe/scripts/test_delphi_v3.py').read())"
python3 -c "import json; json.load(open('delphi-api-safe/evals/evals.json'))"
python3 delphi-docs-sync/scripts/coverage_check.py
grep -rn "endpoints" README.md docs/api-reference.html | grep -oE "[0-9]+ endpoints"   # counts must match
git diff | grep -nE 'dsk-[A-Za-z0-9]{8,}'   # must be empty (placeholder fakes in evals excepted)
```

If the user has provided a key and asked for it, run the live test for the new
endpoint and move its reference entry from *(untested — from docs)* to observed
behavior.

## Step 5 — Commit and push

One conventional commit per logical change (`feat(delphi-api-safe): add X endpoint`),
push immediately to the designated feature branch. State any consciously-skipped
surface in the commit body ("evals: N/A — internal-only endpoint").

## Output format

End with:

| Endpoint | references | SKILL | tests | playground | evals | docs |
|----------|-----------|-------|-------|------------|-------|------|
| `POST /v3/example` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

plus one plain-English line per endpoint on what it does and any tier gate.
