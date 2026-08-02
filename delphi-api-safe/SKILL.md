---
name: delphi-api-safe
description: Safely operate and troubleshoot the Delphi V3 API (conversations, streaming, voice, clone, knowledge-base search) and the Delphi V4 Developer Platform API (contacts/CRM, knowledge-base writes, outbound SMS/email, webhooks, integrations, OpenAI-compatible LLM) for technical and non-technical users. Use when a user asks to test Delphi API keys, run pass/fail checks across accounts, generate curl commands, debug HTTP 4xx/5xx errors, or prepare incident reports. Also use for audience and engagement analytics — sizing an audience ("how many users", "how many real emails", filtering out test/fake accounts) and measuring conversation retention ("retention", "return rate", "how many users came back", "how many have had conversations", repeat-visit and churn analysis from conversation data), including a correctly time-boxed, censoring-corrected "D30 retention" / "30-day retention" / "true 30 day retention" / "cohort retention" number distinct from all-time return-rate metrics. Also trigger when the user says things like "is my clone working", "test this key", "run a smoke test", "check my Delphi", "new Delphi for [name]", "evaluate retention", "v4", "contacts", "upsert a contact", "add to the knowledge base", "set up a webhook", or shares a dsk- or dlph_ API key and wants to verify it. If the user pastes a Delphi API key or mentions Delphi clones, minds, or contacts in any testing, troubleshooting, or audience-analytics context, use this skill.
---

# Delphi API Safe

Run Delphi API tests in a non-destructive, user-safe way. Prefer reproducible checks and clear pass/fail outputs.

Delphi exposes **two live API surfaces**. As of 2026-08-02 **both have chat** —
V4 gained conversations, streaming, and stateless ask. See "Choosing V3 vs V4".

| | V3 — "Delphi External API" | V4 — "Delphi Developer Platform API" |
|---|---|---|
| Base | `https://api.delphi.ai/v3` | `https://api.delphi.ai/v4` |
| Size | 30 paths / 34 ops | 47 paths / 65 ops |
| Chat | ✅ create + SSE stream | ✅ create + SSE stream **+ synchronous send** |
| Only here | voice, KB search, agent, audience analytics | contacts/CRM, KB **writes**, SMS/email, webhooks, integrations, LLM passthrough |
| Envelope | bare objects | `{"data": ...}` (not uniform — check per endpoint) |
| Errors | `{"detail": "..."}` | `{"type","code","message"}` |
| Casing | `snake_case` | `camelCase` |
| Auth | key valid or not | **scoped keys** — a `403` names the missing scope |
| Reference | `references/v3-endpoints.md` | `references/v4-endpoints.md` |

**Key choice matters more than version choice.** A legacy `dsk-` key is
unscoped and works on *everything* in both surfaces. Newer `dlph_` App-Launch
keys are scoped and most **lack `conversations:write`**, so they `403` on V4
chat despite being the newer key style. Their advantage is the 10k req/min rate
limit, not access breadth. Verify with `POST /v4/conversations` before assuming.

## Core rules

- Pick the surface deliberately, then stay on it — **V4 does not contain V3's
  chat/voice/search endpoints, and V3 has none of V4's contacts/content/webhook
  endpoints.** Neither is a superset.
- V3 rate limit: 120 requests per 60 seconds per key. **V4 publishes no numeric
  rate limit** — pace conservatively.
  Supported/tested V3 coverage includes:
  - **Clone**: `GET /v3/clone` — clone profile and identity discovery
  - **Conversations**:
    - `POST /v3/conversation` — create a conversation
    - `POST /v3/stream` — SSE text streaming (supports `file_urls`, `slug`)
    - `GET /v3/conversation/list?email=...` — list conversations for a user
    - `GET /v3/conversation/{id}/history` — message history with optional citations
    - `PUT /v3/conversation/{id}/title` — update conversation title
    - `POST /v3/conversation/{id}/append-clone-message` — inject clone message
    - `DELETE /v3/conversation/{id}` — soft-delete conversation
    - `POST /v3/conversation/ask` — one-off question, no conversation created ⚠️ **currently 502**
    - `GET /v3/conversation/{id}/insights` — insight cards (async; empty is normal)
    - `POST /v3/conversation/{id}/attachments/presign` + `.../{attachment_id}/complete` — two-step file attach (≤10 MB; `status` may be `skipped` on a 200)
  - **Questions**: `GET /v3/questions` — suggested questions (pinned/unpinned/all)
  - **Voice**:
    - `POST /v3/voice/stream` — binary PCM audio streaming (24kHz, 16-bit, mono)
    - `POST /v3/voice/synthesize` — text-to-speech (batch base64 or streaming PCM)
  - **Audience (Users)**:
    - `GET /v3/users` — paginated user list (cursor, active filter)
    - `POST /v3/users/lookup` — lookup by email or phone_number
    - `GET /v3/users/{user_id}/tier`
    - `GET /v3/users/{user_id}/usage`
    - `GET /v3/users/{user_id}/flywheel`
    - `PATCH /v3/users/{user_id}`
    - `POST /v3/users/{user_id}/revoke`
    - `POST /v3/users/{user_id}/activate`
  - **Tags**:
    - `GET /v3/tags`
    - `POST /v3/tags` (with optional `color`)
    - `POST /v3/users/{user_id}/tags/{tag_name}`
    - `DELETE /v3/users/{user_id}/tags/{tag_name}`
  - **User Info**:
    - `GET /v3/users/{user_id}/info`
    - `POST /v3/users/{user_id}/info`
    - `PATCH /v3/users/{user_id}/info/{info_id}` — update existing info item
    - `DELETE /v3/users/{user_id}/info/{info_id}`
  - **Search**:
    - `POST /v3/search/query` — semantic + keyword search across clone's knowledge base
    - `POST /v3/search/content` — search content sources by title or description
  - **Agent**: `POST /v3/agent/run` — autonomous knowledge-base agent; takes an `objective` and returns a synthesized `finalResult` plus a reasoning trace, rather than raw chunks. Heavier than search — use it when the user wants a synthesized answer or multi-hop reasoning, not a chunk lookup.

  Supported/tested **V4** coverage (65 operations; full detail in `references/v4-endpoints.md`):
  - **Conversations** (added 2026-08-02 — requires `conversations:write`):
    - `POST /v4/conversations` — create; `externalId` makes it idempotent (409 on reuse with different input)
    - `POST /v4/conversations/{id}/messages` — **send and wait, no SSE parsing** (the main ergonomic win over V3)
    - `POST /v4/conversations/{id}/messages/stream` — SSE, reuses V3's `CloneResponse` frame contract verbatim
    - `GET /v4/conversations/{id}/insights` — insight cards (needs `insights:read`; async, empty is normal)
    - `POST /v4/conversations/{id}/attachments/presign` + `.../complete` — two-step file attach (≤10 MB)
    - `POST /v4/ask` — stateless Q&A ⚠️ **currently 502**
  - **Profiles**: `GET /v4/profile` (identity discovery — the V4 analogue of `/v3/clone`), `GET /v4/profile/questions` (replaces `/v3/questions`), `GET /v4/profiles/{username}`
  - **Contacts** (the V4 evolution of `/v3/users`):
    - `GET /v4/contacts` — cohort list with far richer server-side filtering (search, tags, access tier, opt-in, interaction counts, date ranges, sort)
    - `POST /v4/contacts` — **email-keyed upsert that returns `wasCreated`**, removing the insert-vs-match ambiguity of `/v3/users/lookup`
    - `GET /v4/contacts/{id}`, `PATCH /v4/contacts/{id}` (access tier only)
    - `GET /v4/contacts/{id}/threads` — conversations with narrative summaries
  - **Contact tags**: `GET|POST /v4/contact-tags`, assign/unassign per contact, `POST /v4/contacts/bulk/tags` (bulk add/remove by IDs or filter)
  - **Contact properties**: custom owner-defined fields — definitions + per-contact values (no V3 equivalent)
  - **Content (knowledge-base writes)**: `GET|POST /v4/content`, `GET|PATCH|DELETE /v4/content/{id}` — create QA pairs, notes, and URLs; editing a body **re-learns** it. V3 could only *search* content.
  - **Generate / Send / Notify**: `POST /v4/generate` (owner-voice text, **no retrieval**, daily owner budget), `POST /v4/send` (**real SMS/email to a contact**), `POST /v4/notify-owner`
  - **LLM**: `POST /v4/llm/chat/completions` — OpenAI-compatible, voiceless, non-streaming
  - **Webhooks**: `GET|POST /v4/webhook-subscriptions`, `GET|PUT|DELETE /v4/webhook-subscriptions/{id}` — 9 event types
  - **Integrations** (21 ops): deploy bundled code triggered by events or cron — lifecycle, source, secrets, triggers, delivery log
  - **Data deletion**: `POST /v4/data-deletion-requests` — irreversible, queues contact data deletion
- See `references/v3-endpoints.md` and `references/v4-endpoints.md` for request/response expectations and known quirks.
- Never invent user data (emails, API keys, clone names, webhook URLs). Users often share test output with teammates or paste it into tickets — invented data causes confusion and erodes trust.
- If a required field is missing, ask a direct question before proceeding.
- Treat API keys as sensitive secrets. Redact keys in user-visible output (e.g., `dsk-****WmQ`) or use `$DELPHI_API_KEY`. Users frequently share screens or copy chat logs, so a leaked key can be exploited within minutes. Don't echo raw keys back, even if the user provided them — the output may end up somewhere the user didn't intend.
- For non-technical users, provide copy-paste commands and plain-English interpretation.
- **V4 raises the blast radius of a mistake.** The worst accidental V3 write
  renamed a user; V4 can message a real person, delete knowledge, or deploy
  code. Never call these without explicit, per-call user confirmation:
  `POST /v4/send` · `POST /v4/data-deletion-requests` · `DELETE /v4/content/{id}` ·
  any integrations publish/activate/push/delete · `PUT /v4/integrations/{id}/secrets/{name}`.
  Treat `POST /v4/generate` and `POST /v4/llm/chat/completions` as metered — safe
  but not free.

## Choosing V3 vs V4

Ask what the user is trying to *do*, then route:

| The user wants to… | Surface | Endpoint |
|---|---|---|
| Test that a clone works (smoke test) | **V3** | `/v3/conversation` + `/v3/stream` — the established harness |
| Chat, streaming tokens | **either** | `/v3/stream` or `/v4/conversations/{id}/messages/stream` (same SSE frame contract) |
| Chat, **without** parsing SSE | **V4** | `POST /v4/conversations/{id}/messages` — synchronous, returns the full reply |
| Avoid duplicate conversations on retry | **V4** | `POST /v4/conversations` with `externalId` |
| Attach a file to a conversation | **either** | two-step presign → complete (both surfaces, added 2026-08-02) |
| Voice audio or TTS | **V3 only** | `/v3/voice/*` |
| Search or reason over the knowledge base | **V3 only** | `/v3/search/query`, `/v3/agent/run` |
| Audience sizing / retention analytics | **V3** | `/v3/users` + `/v3/conversation/list` (`scripts/audience_audit.py`) |
| Add / edit / delete knowledge-base content | **V4** | `/v4/content` |
| Manage contacts, custom fields, segments | **V4** | `/v4/contacts`, `/v4/contact-properties/*`, `/v4/contacts/bulk/tags` |
| Create a contact and know if it was new | **V4** | `POST /v4/contacts` → `wasCreated` |
| Text or email a contact | **V4** | `/v4/send` (consent enforced server-side) |
| React to Delphi events | **V4** | `/v4/webhook-subscriptions` or `/v4/integrations` |
| Use Delphi as a plain LLM | **V4** | `/v4/llm/chat/completions` |
| One-shot Q&A, no conversation state | ⚠️ **neither** | `/v3/conversation/ask` and `/v4/ask` both return `502` — see below |

Rules of thumb:

- **Chat now exists on both.** Route on *capability*, not version: V4 if you want
  the synchronous send or idempotent create; V3 if voice or KB search is in the
  same flow. Check the key holds `conversations:write` before choosing V4.
- **Voice, KB search, and the agent are V3-only.** No V4 equivalent.
- **Writes to the knowledge base or the audience are V4-only.**
- When a task spans both (e.g. "find users who churned, then email them"), use V3
  for the analysis and V4 for the action — say so explicitly, so the user knows
  two surfaces are involved.
- Don't migrate working V3 code to V4 for its own sake.

### ⚠️ V4 conversation creation is eventually consistent

`POST /v4/conversations` returns a `conversationId` **before the underlying
thread exists**. Sending a message immediately fails with
`404 resource_not_found` / `"Thread not found"`. Measured ready after **~2–6s**.

**Retry the send on `404` with ~1s backoff** (up to ~5 attempts). A 404 right
after create means "not ready yet", not "wrong id" — don't send the user
chasing a bad conversation id. `scripts/test_delphi_v4.py` implements this.

### ⚠️ Known outage: the stateless `ask` endpoints

`POST /v3/conversation/ask` and `POST /v4/ask` **both return `502`
(`dependency_failure` / `experience_stream_incomplete`) for every caller.**
Verified deterministic — 0 successes in 24+ attempts across clones, key styles,
and fully-scoped keys. Reported to Delphi 2026-08-02.

**Do not debug this on the user's behalf** — it is not their key, scope, or
payload. A scope problem returns `403` naming the scope; this is `502`.
Recommend the two-call workaround (`POST /v4/conversations` then
`POST /v4/conversations/{id}/messages`) and re-test before relying on `ask`.

## Clone discovery

When the user provides a key but no clone name:
1. Call `GET /v3/clone` with that key — it returns the clone profile including name and other metadata
2. If that returns 403, the key may not be active yet — report this clearly
3. If it returns 200, use the discovered clone identity in test results and reporting
4. Never guess clone identities — prefer API discovery over invention

## Required user inputs

Collect the minimum needed for the requested task:

1. **Goal**: what they want to test (single clone, full account sweep, incident report, etc.)
2. **Credential source**:
   - API key(s), or
   - permission to discover from their provided files/context
3. **Test prompt** (optional): use a default only if user does not care

When the user's message already contains most of the info, ask only for what's missing — don't repeat a full questionnaire if they've given 2 of 3 inputs. See `references/intake-checklist.md`.

## Workflow

1. **Confirm scope**
   - Single clone test, or multi-account matrix.
2. **Self-discover what you can**
   - Use `GET /v3/clone` to identify the clone behind each key.
   - Reuse provided keys from user message or known workspace docs.
   - Do not guess unknown values.
3. **Run baseline API checks**
   - `clone` profile check first (also validates the key).
   - `conversation` check second.
   - `stream` check third with returned `conversation_id`.
4. **Classify results**
   - PASS: conversation 200 + stream returns SSE (`data:`) and completion marker (`[DONE]`).
   - FAIL: any non-200, empty stream, missing done marker, invalid JSON payload.
5. **Report clearly**
   - Provide a grid with Account, Key (redacted), Clone, Conversation, Stream, Overall, Note.
   - Include one known-good sample and one failure sample when relevant.
6. **Escalation package**
   - Include repro steps, expected/actual, conversation IDs, and timestamps.

## Example output

**Single clone test — PASS:**

| Account | Key | Clone | Conversation | Stream | Overall |
|---------|-----|-------|-------------|--------|---------|
| Jay Shetty | `dsk-****draE` | Jay Shetty | PASS | PASS | **PASS** |

**Failed key — 403 on all endpoints:**

| Account | Key | Clone | Conversation | Stream | Overall |
|---------|-----|-------|-------------|--------|---------|
| Unknown | `dsk-****qlwI` | — | FAIL (403) | — | **FAIL** |

Note: 403 on all endpoints typically means the key is not active or not yet authorized.

## Audience & retention analytics

Beyond pass/fail key checks, this skill measures **who is in an audience** and
**whether they come back**. Use `scripts/audience_audit.py` (read-only) for both.

### 1. Audience sizing — focus on REAL emails

`GET /v3/users` returns the *raw* audience, which is padded with test, smoke, and
integration addresses. The number that matters for any real metric is **real
users**, not the raw total. An email is **real** when it has a plausible
address (an `@`, a dotted domain, a non-empty local part) and contains none of
these markers: `example`, `fake`, `test`, `noinput`, `smoke`, `placeholder`,
`dummy`, `invalid`, `no-reply`/`noreply`. Always report **total / real /
filtered-out** as three separate numbers — never quote the raw total as if it
were the real audience.

### 2. Conversation retention — the real return signal

Retention is measured from each conversation's **`created_at` timestamp** (via
`GET /v3/conversation/list?email=...`), not a yes/no "has a conversation" flag.
Among real users with ≥1 conversation, report:

- **Return rate** — % with ≥2 conversations (came back at least once).
- **Multi-day rate** — % active on ≥2 distinct UTC calendar days. **This is the
  truest *all-time* retention number** — multiple conversations on the *same* day
  can be one session split up; a new day is a genuine repeat visit. Lead with
  this when the user wants an unbounded, lifetime signal. But it is **not** a
  30-day metric — it never expires and isn't comparable across differently-aged
  clones. If the user specifically asks for "D30", "30-day", or "true/cohort
  retention," use `scripts/d30_retention.py` (below) instead — this all-time
  number will misrepresent that ask.
- **Recency / churn** — days since each user's last conversation (`≤7d`, `8–30d`,
  `31–90d`, `>90d`), benchmarked against the clone's age.
- **Depth** — conversations-per-user distribution (`1`, `2–3`, `4–10`, `11+`).

**Always report the median, not just the mean.** A single integration/owner
account with thousands of conversations (often `medium: API`) inflates the
average; flag that outlier and quote the median as the real central tendency.

### Run it

```bash
# Full audit (audience sizing + retention). --account reads keys.json; or use --api-key.
python3 scripts/audience_audit.py --account <name>
python3 scripts/audience_audit.py --api-key "$DELPHI_API_KEY"

# Audience sizing only (fast — skips the per-user conversation pull):
python3 scripts/audience_audit.py --api-key "$DELPHI_API_KEY" --no-retention

# Machine-readable, and cache raw per-user data locally (PII — keep out of git):
python3 scripts/audience_audit.py --account <name> --json --cache <name>.cache.json
```

Notes: the script sweeps users at `limit=200` (the real API max — `limit=1000`
was a docs/code bug in an earlier version of this skill and 400s; see
`references/v3-endpoints.md`), sets a custom User-Agent (Cloudflare 403s the
default `python-urllib` UA), retries Delphi's intermittent `500`s on
`/v3/conversation/list`, and paces under the 120 req/60s limit. A full
retention pass makes one `conversation/list` call per real user, so it takes a
few minutes for large audiences — run it in the background.

### 3. D30 retention — the correctly-defined, time-boxed 30-day rate

`audience_audit.py`'s return-rate and multi-day-rate are **all-time** — they
never expire, so they aren't "30-day retention" no matter how they get
described. When the user specifically asks for **D30 / 30-day / true / cohort
retention**, use `scripts/d30_retention.py` instead. It answers one precise
question: *of users whose first conversation fell in a 30-day acquisition
window, what % had another conversation in the following 30 days?*

The window is always the **last `--window-days` (default 60), split into two
equal 30-day halves** ending "now" (or ending at the data's own last timestamp
in export-only mode):

```
[reference-60d ... reference-30d)   acquisition half  -> cohort membership
[reference-30d ... reference]       return-check half -> did they come back?
```

Because the return-check half always ends exactly at `reference`, every cohort
member has had a full, uncensored 30 days to return — no need to drop a
"too-recent-to-judge" tail the way a naive whole-window calculation would.

**Three data sources, one calculation** (pick with flags, not a mode switch):

| Flags | Speed | Accuracy | When to use |
|---|---|---|---|
| `--export FILE` only | fast, local | approximate — "first conversation" means first appearance *in the file*, so a long-lapsed user reappearing near the window start can misclassify as "new" | quick gut-check, no API budget wanted |
| `--account NAME` only | slow — one API call per real user in the **entire** audience | most authoritative — `/v3/conversation/list` returns full, uncapped history | small clones, or no export on hand |
| `--export FILE --account NAME` (**combo**, recommended default when both exist) | fast **and** authoritative | uses the export only to find who was active in the window (cheap, local), then hits the API just for those candidates to pull their true full history | the default choice whenever an export is available |

Combo mode also reports **coverage** — what % of the *live* real audience
appears anywhere in the export. On one clone tested, coverage was only ~29%:
71% of the registered audience had zero conversations in the trailing 60 days
and would be invisible to an export-only analysis. Always surface this number
alongside the D30 rate; a low coverage figure means most of the audience is
dormant, which is a different (and often more urgent) problem than retention
among the users who do show up.

**Key selection — always prefer the high-rate-limit key.** Legacy `dsk-` keys
are capped at 120 req/60s; App-Launch `dlph_` keys carry a much higher
published cap and are what new clones get provisioned with going forward. The
script auto-detects this: pass a legacy `--account name` and, if a
`name_applaunch` sibling exists in `keys.json`, it transparently swaps to the
`dlph_` key and paces faster — you don't need to know the exact handle. It
still paces `dlph_` keys deliberately (not zero-delay): a rapid burst has been
observed to draw a `429` even on a high-rate-limit key, so "high limit" is not
"no limit."

```bash
# Fast, local, approximate
python3 scripts/d30_retention.py --export conversations.ndjson

# Slow, full-audience live sweep, most authoritative on its own
python3 scripts/d30_retention.py --account <name>

# COMBO — fast + authoritative (recommended whenever an export exists)
python3 scripts/d30_retention.py --export conversations.ndjson --account <name>

# Override the window (e.g. D60 instead of D30) or get machine-readable output
python3 scripts/d30_retention.py --export conversations.ndjson --account <name> --window-days 90 --json
```

Report the headline `D30 RETENTION RATE` as the single clear number — don't
present it alongside `audience_audit.py`'s all-time return/multi-day rates as
if they're interchangeable options; they answer different questions and
mixing them without labels is how a stakeholder ends up quoting the wrong one.

## Standard commands

### Discover clone

```bash
curl -sS -X GET "https://api.delphi.ai/v3/clone" \
  -H "x-api-key: $DELPHI_API_KEY"
```

### Create conversation

```bash
curl -sS -X POST "https://api.delphi.ai/v3/conversation" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### Stream message

```bash
curl -i -N -X POST "https://api.delphi.ai/v3/stream" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"<prompt>","conversation_id":"<cid>"}'
```

### List conversations

```bash
curl -sS "https://api.delphi.ai/v3/conversation/list?email=user@example.com" \
  -H "x-api-key: $DELPHI_API_KEY"
```

### Get conversation history

```bash
curl -sS "https://api.delphi.ai/v3/conversation/<cid>/history?include_citations=true" \
  -H "x-api-key: $DELPHI_API_KEY"
```

### Get suggested questions

```bash
curl -sS "https://api.delphi.ai/v3/questions?type=pinned&count=5" \
  -H "x-api-key: $DELPHI_API_KEY"
```

### List users (paginated)

```bash
curl -sS "https://api.delphi.ai/v3/users?limit=20" \
  -H "x-api-key: $DELPHI_API_KEY"
```

### One-liner test

```bash
CID=$(curl -sS -X POST "https://api.delphi.ai/v3/conversation" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["conversation_id"])') && \
echo "CID=$CID" && \
curl -i -N -X POST "https://api.delphi.ai/v3/stream" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"<prompt>\",\"conversation_id\":\"$CID\"}"
```

### Search knowledge base

```bash
curl -sS -X POST "https://api.delphi.ai/v3/search/query" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": ["<semantic query>"], "keywords": ["<keyword>"], "limit": 5}'
```

### Search content sources

```bash
curl -sS -X POST "https://api.delphi.ai/v3/search/content" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": ["<topic or title>"]}'
```

### Run knowledge-base agent (synthesized answer, not raw chunks)

```bash
curl -sS -X POST "https://api.delphi.ai/v3/agent/run" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"objective": "<question or task>", "thinking_time": 10}'
```

## Standard commands (V4)

All V4 responses wrap in `{"data": ...}` unless noted. Errors are
`{"type","code","message"}`, not V3's `{"detail"}`.

### Identity check (V4 equivalent of the clone check)

```bash
curl -sS "https://api.delphi.ai/v4/profile" \
  -H "x-api-key: $DELPHI_API_KEY"
```

### Chat without SSE — create, then send and wait

```bash
curl -sS -X POST "https://api.delphi.ai/v4/conversations" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
# -> {"data":{"conversationId":"...","existed":false}}
```

```bash
curl -sS -X POST "https://api.delphi.ai/v4/conversations/<conversationId>/messages" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text":"<message>"}'
# -> {"data":{"text":"<full reply>","citations":[],"parts":[...]}}
```

### Chat with SSE (same frame contract as /v3/stream)

```bash
curl -i -N -X POST "https://api.delphi.ai/v4/conversations/<conversationId>/messages/stream" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text":"<message>"}'
```

### Check whether a key holds `conversations:write`

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://api.delphi.ai/v4/conversations" \
  -H "x-api-key: $DELPHI_API_KEY" -H "Content-Type: application/json" -d '{}'
# 200 = has the scope | 403 = missing it (response names the scope)
```

### List contacts (cursor-paginated, limit max 200)

```bash
curl -sS "https://api.delphi.ai/v4/contacts?limit=50&sort=lastActive&direction=desc" \
  -H "x-api-key: $DELPHI_API_KEY"
```

### Upsert a contact — tells you whether it was created

```bash
curl -sS -X POST "https://api.delphi.ai/v4/contacts" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email": "<email>", "name": "<name>", "tags": ["<tag>"]}'
# -> {"data":{"contactId":"...","wasCreated":true|false}}
```

### Add a Q&A pair to the knowledge base (async — poll for COMPLETE)

```bash
curl -sS -X POST "https://api.delphi.ai/v4/content" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"items": [{"type": "qa", "question": "<q>", "answer": "<a>"}]}'
```

```bash
curl -sS "https://api.delphi.ai/v4/content/<content_id>" \
  -H "x-api-key: $DELPHI_API_KEY"
```

### Generate in the mind's voice (metered; idempotency key makes retries safe)

```bash
curl -sS -X POST "https://api.delphi.ai/v4/generate" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "<instruction>", "idempotencyKey": "<unique-id>"}'
# -> {"data":{"text":"...","budgetRemaining":9999,"replayed":false}}
```

### OpenAI-compatible completion (no `data` envelope — raw OpenAI shape)

```bash
curl -sS -X POST "https://api.delphi.ai/v4/llm/chat/completions" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "<prompt>"}]}'
```

### Fetch either spec (both require a valid key)

```bash
curl -sS "https://api.delphi.ai/v4/openapi.json" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -A "delphi-api-safe/1.0"
```

## Non-technical UX rules

- Explain each result in one line: "Create worked, stream failed with 500".
- Redact secrets in all summaries, tables, and examples.
- When user pastes broken command output, identify if issue is:
  - command syntax,
  - JSON formatting,
  - or backend failure.
- If backend failure is reproducible, generate a ready-to-send incident report.

## Key handling and storage policy

- Default to ephemeral key handling in-memory.
- If local persistence is needed (`smoke-config.json`), store only on the user's machine.
- Never commit credential files.
- User can "throw away" stored key anytime by deleting `smoke-config.json` or replacing the key with a blank value.

## Use bundled script

For reliable repeated testing, run chat mode:

```bash
python3 scripts/test_delphi_v3.py --api-key "$DELPHI_API_KEY" --mode chat
```

Run full mode (users/tags/info included):

```bash
python3 scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode full \
  --user-email "<real-user-email>"
```

Run search tests (Immortal plan):

```bash
python3 scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode chat \
  --test-search \
  --search-query "What is your background?"
```

Run the knowledge-base agent test (heavier/slower than search — synthesizes an answer with a reasoning trace instead of returning raw chunks):

```bash
python3 scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode chat \
  --test-agent \
  --agent-objective "Summarize the key themes covered in the knowledge base." \
  --agent-thinking-time 10
```

Enable write endpoint tests only with explicit consent:

```bash
python3 scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode full \
  --user-email "<real-user-email>" \
  --allow-write \
  --tag-name "<tag-name>" \
  --info-text "<safe-test-note>"
```

The script prints structured JSON suitable for incident docs.
