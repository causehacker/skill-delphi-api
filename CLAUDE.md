# CLAUDE.md — Operating Manual for skill-delphi-api

This repo builds and ships **Claude Skills for operating the Delphi V3 API**
(digital-clone platform at api.delphi.ai), plus a browser test playground and
deterministic smoke-test tooling. The owner (Jim) manages multiple production
Delphi clones; the tools here run against **live production accounts with real
customer PII**. Act accordingly.

## Repo map

| Path | What it is | Edit it when |
|------|-----------|--------------|
| `delphi-api-safe/SKILL.md` | The shipped skill: rules + workflow + commands | Any endpoint or workflow change |
| `delphi-api-safe/references/v3-endpoints.md` | **Source of truth** for observed API behavior | Any new endpoint or newly observed quirk |
| `delphi-api-safe/scripts/test_delphi_v3.py` | Deterministic endpoint tester (JSON output) | Any new endpoint |
| `delphi-api-safe/scripts/audience_audit.py` | Read-only audience sizing + retention analytics | Analytics methodology changes |
| `delphi-api-safe/evals/evals.json` | Natural-language trigger evals for the skill | Any new skill capability |
| `docs/api-reference.html` | Single-file interactive playground (vanilla JS) | Any new endpoint |
| `docs/serve.py` | Local CORS proxy (`/api/*` → api.delphi.ai) | Rarely — only for new response types (SSE/binary) |
| `docs/HOW-TO.md`, `docs/CLAUDE-QUICKSTART.md`, `README.md` | User docs | Any new capability or make target |
| `scripts/run_smoke.py`, `scripts/setup.py`, `Makefile`, `smoke-config.example.json` | Smoke-test harness + config wizard | Any new test flag or config field |
| `dist/delphi-api-safe.skill` | Packaged artifact — **generated, never hand-edit** | Only via `make package` (runs on Jim's machine) |

## The Fan-Out Rule (the #1 mistake to avoid)

**A new or changed endpoint is not "done" until it exists on every surface.**
The most common failure mode in this repo is updating one file and stopping.
The full checklist for any endpoint addition/change:

1. `delphi-api-safe/references/v3-endpoints.md` — method, path, body/query fields, response shape, quirks
2. `delphi-api-safe/SKILL.md` — endpoint list entry + a curl example under "Standard commands" if user-facing
3. `delphi-api-safe/scripts/test_delphi_v3.py` — a `test_*` function, wired into `main()`, plus a `*_summary` block
4. `docs/api-reference.html` — an `ENDPOINTS` array card (and bump the endpoint count in the page subtitle **and** in README.md)
5. `delphi-api-safe/evals/evals.json` — at least one natural-language eval with the next sequential id
6. `README.md` + `docs/HOW-TO.md` — coverage lists, script examples, make targets
7. If the endpoint needs a new CLI flag: `scripts/run_smoke.py`, `scripts/setup.py`, `smoke-config.example.json`, `Makefile`

Run `python3 delphi-docs-sync/scripts/coverage_check.py` to verify parity
across surfaces before committing.

## Security rules (non-negotiable, in priority order)

1. **Never commit a credential.** Before every commit: `git diff --cached | grep -nE 'dsk-[A-Za-z0-9]{8,}|sk-|ghp_|Bearer '` must return nothing. Placeholders (`dsk-abc123XYZ` style obvious fakes in evals) are the only exception.
2. **Redact keys in every user-visible output**: format `dsk-****<last3-4>`. This includes tables, logs, incident reports, commit messages, and chat replies — even when the user pasted the key themselves.
3. **PII stays local.** `keys.json`, `smoke-config.json`, `*.cache.json`, `out/` are gitignored on purpose. Analysis output containing emails or conversation data goes in `out/` or a scratch dir, never into tracked files.
4. **Read-only by default.** Any endpoint that mutates state (POST/PUT/PATCH/DELETE on users, tags, info, conversations) requires the user's explicit opt-in in the current conversation. `--allow-write` exists for exactly this; never pass it on your own initiative. These are production clones — a "test" PATCH renames a real customer.

## House conventions

- **Python**: stdlib only (`urllib`, `argparse`, `json`, `statistics`). No pip installs, no requirements.txt. New analytics-style scripts follow `audience_audit.py`'s pattern: `urllib` + custom `User-Agent` + retry-with-backoff. `test_delphi_v3.py` uses curl-subprocess; keep that file consistent with itself.
- **HTML tools**: one self-contained file, vanilla JS, zero build step, no CDN. New playground endpoints are data (an `ENDPOINTS` array entry with `body`/`query`/`extra`/`bodyFn`/`queryFn`/`pathFn`), not new code.
- **Test function shape** in `test_delphi_v3.py`: return a dict with `"<name>": "PASS"|"FAIL"`, `"<name>_http": <status>`, `"note": ""` on pass / short reason on fail, previews truncated to ≤280 chars. Wire into `main()` and add a `*_summary` block.
- **references/v3-endpoints.md records observed reality**, not documentation claims. When a live response differs from the docs (e.g. `/v3/clone` wraps its payload in a `"clone"` key; `/v3/conversation/list` throws intermittent 500s), write down what actually happened and how to handle it.
- **Commits**: conventional style (`feat:`, `fix:`, `refactor:`, `security:`, `docs:`), imperative, optionally scoped `feat(delphi-api-safe):`. One logical change per commit. **Push immediately after committing** — a stop hook flags unpushed commits.
- **Git flow**: work on the designated feature branch, never push to `main`. Do not open a PR unless asked. If the branch's PR was merged, rebase the branch onto `origin/main` before new work.
- **Analytics methodology** (do not regress these): report **total / real / filtered-out** users as three numbers — never quote the raw total as the audience (raw lists are padded with test/smoke emails; see `is_real()` in `audience_audit.py`). Report the **median** conversations-per-user, not the mean (integration accounts skew it). **Multi-day rate** (≥2 distinct UTC days) is the headline retention number, not return rate.

## API facts that will bite you

- Base URL `https://api.delphi.ai`, auth via `x-api-key` header, one key = one clone.
- **Rate limit: 120 requests / 60 seconds per key.** Sweeping scripts must pace (`time.sleep`) and back off on 429.
- **Cloudflare 403s the default `python-urllib` User-Agent.** Always set a custom UA in urllib scripts.
- `GET /v3/conversation/list` returns **intermittent 500s** — retry with backoff before concluding anything; a 500 is not "no conversations".
- Some clones 500 on `/v3/stream` while others pass — a single-clone stream failure is a per-clone incident, not a code bug.
- 403 on all endpoints = key not active/authorized. Say that; don't debug the code.
- **docs.delphi.ai returns 403 to WebFetch/curl** (auth-gated). Do not spin retrying it. Get docs via the `delphi-help-center` MCP server if connected this session; otherwise ask Jim to paste the page (he will). The `.md` suffix trick does not work either.
- Search endpoints (`/v3/search/*`) are **Immortal-plan only** — a 403/404 there on a lower-tier clone is expected, not a failure.
- User info POST body field is **`info`** (not `text`); `PATCH /users/{id}/info/{id}` needs at least one of `info`/`info_type`.

## Named mistakes → the rule that prevents each

| Mistake a weaker model will make | Rule |
|---|---|
| Adds endpoint to the test script, forgets playground/evals/docs | Fan-Out Rule checklist above; run `coverage_check.py` |
| Echoes a pasted API key back in a reply or table | Redact to `dsk-****<last4>` the moment you see it |
| Runs `--allow-write` or a DELETE "to be thorough" | Mutations require explicit user opt-in in the current conversation |
| `pip install requests` or adds an npm build | Stdlib/vanilla-JS only; if you think you need a dependency, you don't |
| Reports raw user count as the audience | Always total / real / filtered-out, three numbers |
| Quotes mean conversations-per-user | Median headline, mean only with the outlier flagged |
| Hammers the API in a loop and hits 429 | Pace under 120 req/60s; sleep between paginated calls |
| Treats one 500 from `conversation/list` as truth | Retry with backoff (5 tries, 1.5s × attempt) first |
| Burns turns re-fetching docs.delphi.ai after a 403 | One try; then MCP server or ask Jim to paste |
| Hand-edits `dist/delphi-api-safe.skill` | Generated artifact; only `make package` touches it |
| Updates endpoint count in the HTML but not README (or vice versa) | Grep for the old count: `grep -rn "N endpoints" README.md docs/` |
| Invents a test email / clone name / webhook URL to fill a gap | Never invent user data; ask, or use `GET /v3/clone` to discover |
| Writes docs-claimed behavior into v3-endpoints.md without testing | That file records *observed* behavior; mark untested items as such |
| Commits then stops | Push immediately; the stop hook will flag you |

## Quality bar per deliverable (checkable)

**New endpoint integration**
- [ ] All 7 fan-out surfaces updated (or consciously N/A, stated in the commit body)
- [ ] `python3 -c "import ast; ast.parse(open('delphi-api-safe/scripts/test_delphi_v3.py').read())"` passes
- [ ] `python3 -c "import json; json.load(open('delphi-api-safe/evals/evals.json'))"` passes
- [ ] curl example uses `$DELPHI_API_KEY`, never a literal key
- [ ] Endpoint counts consistent between `docs/api-reference.html` subtitle and `README.md`
- [ ] `coverage_check.py` shows no new gaps

**New/changed script**
- [ ] Stdlib only; runs under `python3` with no setup
- [ ] `--help` is accurate; supports `--json` if it produces a report
- [ ] Redacts any key it prints; paces API calls; retries 429/5xx
- [ ] Read-only unless the script's whole purpose is writing (then gated by an explicit flag)

**Docs change**
- [ ] Every command shown was actually run or syntax-verified
- [ ] Plain-English one-line interpretation accompanies any technical result format
- [ ] No unredacted keys, real emails, or real conversation IDs in examples

**Skill change (SKILL.md)**
- [ ] Frontmatter `description` updated if triggers changed (it's the routing signal)
- [ ] New capability has ≥1 eval in `evals/evals.json`
- [ ] Rules are written for a less-capable executor: imperative, concrete, no "use judgment"

**Commit/push**
- [ ] Conventional-style message; body explains the why for non-obvious changes
- [ ] Credential grep on the staged diff is clean
- [ ] Pushed to the designated feature branch, `-u origin <branch>`

## When uncertain — exact escalation rules

1. **Missing API documentation** (new endpoint, unknown field): try the `delphi-help-center` MCP once if available; otherwise ask Jim to paste the docs page. Do not guess request/response shapes into tracked files.
2. **Docs contradict observed behavior**: trust the live response, record both in `v3-endpoints.md` ("docs say X, observed Y"), and mention the discrepancy in your reply.
3. **Need a real credential/email/account**: ask. Never fabricate, never reuse a key from an unrelated context. `keys.json` (local, gitignored) is the sanctioned key registry for multi-account scripts.
4. **A change would mutate production data** (users, tags, info, conversations — including "harmless" test writes): state what would be written and get a yes first. Deleting/revoking always requires an explicit yes, every time.
5. **Ambiguous scope** (e.g. "update the skill" could mean 3 files or 12): make the smallest reasonable interpretation, state it in one sentence, and proceed — don't stall on a questionnaire. Ask only when the interpretations genuinely diverge in effect.
6. **Destructive git operations** (force-push, history rewrite, branch deletion): only with explicit instruction, except force-with-lease when restarting a branch whose PR already merged (per the merged-PR rule).
7. **Anything failing repeatedly** (3 attempts at the same fix): stop, summarize what was tried and observed, and hand the decision back with your best hypothesis.
