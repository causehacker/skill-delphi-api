# Delphi V3 Endpoints - Tested Coverage and Notes

This file captures endpoint behavior learned from real tests, cross-checked
against the live spec at `GET /v3/openapi.json` (requires a valid `x-api-key`;
the default UA is 403'd by Cloudflare, same as other endpoints — set a custom
`User-Agent`). Last cross-checked 2026-08-01 against `openapi: 3.1.0`.

Base URL: `https://api.delphi.ai`
Authentication: `x-api-key` header on every request (key scoped to a single clone).
Rate limits: 120 requests per 60 seconds per API key. Exceeding returns `429`.

## Clone

- `GET /v3/clone`
  - Expected: `200` + JSON with clone profile
  - Response wraps in `"clone"` key: `{ "clone": { ... } }`
  - Response fields: `id`, `name`, `slug`, `description`, `headline`, `purpose`, `tags` (string[]), `imageUrl`, `initial_message`
  - This is the primary way to identify which clone a key belongs to. Call it first when testing a new key.
  - If 403: key is not active or not authorized. Report this to the user immediately.

## Conversations

- `POST /v3/conversation`
  - Expected: `200` + `conversation_id`, `created_at`, `initial_message`
  - Body: `{}` (empty JSON is sufficient) or `{"user_email": "..."}` to associate with a user
  - Optional body field: `slug` (string) — same clone-scoping purpose as the `slug` field on `/v3/stream`

- `POST /v3/stream`
  - Expected: `200` + SSE `data:` chunks + `[DONE]`
  - Body: `{"message": "...", "conversation_id": "..."}`
  - Optional body fields: `file_urls` (string[], uploaded file URLs), `slug` (clone slug)
  - Known issue: some clones return `500 Internal Server Error` while others pass.

- `GET /v3/conversation/list`
  - List all conversations for a user under this clone
  - Query: `?email=<user-email>` (required)
  - Response: `{ "conversations": [{ "id", "title", "created_at", "medium" }] }`
  - Sorted by newest first. Only active (non-deleted) conversations returned.
  - `medium` values seen: `EMBED`, `WEB`, `API`, `BROWSER_VOICE`.
  - **Intermittent `500`** on some emails — retry with backoff (it usually
    succeeds within a few attempts; do not count a 500 as "no conversations").
  - Returns the *full* list (no observed cap — one user came back with 2,394),
    so per-user counts are trustworthy for retention math.
  - **Retention methodology**: this is the primary retention signal. Per real
    user, derive: return rate (≥2 conversations), multi-day rate (≥2 distinct
    `created_at` calendar days — the truest signal), recency (days since the
    newest `created_at`), and conversations-per-user depth. Report the **median**
    per-user count, not the mean — an integration/owner account with thousands
    of `medium: API` conversations skews the average. See
    `scripts/audience_audit.py`.

- `GET /v3/conversation/{conversation_id}/history`
  - Retrieve full message history for a conversation
  - Query: `?include_citations=true|false` (optional, default false)
  - Response: `{ "messages": [{ "id", "text", "sender", "created_at", "citations" }] }`
  - sender values: `CLONE`, `USER`
  - Citation fields (when include_citations=true): `url`, `text`, `type` (WEB|PDF|TWITTER), `title`, `page_num`, `timestamp`, `tweet_id`, `citation_url`
  - Messages returned in chronological order (oldest first).

- `PUT /v3/conversation/{conversation_id}/title`
  - Set or update conversation title (1-500 characters)
  - Body: `{"title": "..."}`
  - Response: `{ "id", "title", "updated_at" }`

- `POST /v3/conversation/{conversation_id}/append-clone-message`
  - Inject a message into a conversation as if the clone said it
  - Body: `{"text": "..."}`  (1-50,000 chars)
  - Response: `message_id`, `conversation_id`, `text`, `sender`, `created_at`
  - Use case: onboarding flows, scripted intros, seeding context

- `DELETE /v3/conversation/{conversation_id}`
  - Soft-delete a conversation (hidden, not permanently removed)
  - Response: `{ "status": "archived" }`

## Questions

- `GET /v3/questions`
  - Retrieve suggested questions configured for the clone (conversation starters)
  - Query params:
    - `type`: `pinned` (default) | `unpinned` | `all`
    - `count`: 1-100 (default 5)
    - `randomize`: true|false (default false)
  - Response: `{ "questions": [{ "id", "index", "question", "pinned", "user_edited", "created_at", "updated_at" }] }`
  - Default sort: by `index` descending. Use `randomize=true` to shuffle.

## Voice

- `POST /v3/voice/stream`
  - Expected: `200` + raw binary PCM audio
  - Audio format: 24kHz sample rate, 16-bit signed little-endian, mono
  - Body: `{"message": "...", "conversation_id": "..."}`
  - Response headers include `X-Audio-*` metadata (sample rate, format, etc.)
  - Response is streamed — read in chunks (8192 bytes recommended)
  - Requires clone to have a voice configured; returns error if not available
  - PCM-to-Float32 conversion: `Int16Array` value / 32768

- `POST /v3/voice/synthesize`
  - Text-to-speech: converts text to audio without needing a conversation
  - Body: `{"text": "..."}`  (1-10,000 chars)
  - Query param: `?stream=true` for raw PCM stream, omit for base64 JSON response
  - Batch response (default): `{"audio": "<base64-encoded PCM>"}`
  - Streaming response: same binary PCM format as /v3/voice/stream
  - Same `X-Audio-*` headers when streaming
  - Requires clone to have a voice configured

## Audience (Users)

- `GET /v3/users`
  - Paginated list of all users in the audience
  - Query params:
    - `limit`: page size 1-200 (default 50). **Not 1000** — `limit>200` returns
      `400 {"detail":"Invalid request"}`. This is confirmed both empirically
      (tested across 6+ clones and both `dsk-`/`dlph_` key styles, 2026-07-23)
      and in the live OpenAPI schema (`maximum: 200`). An earlier version of
      this doc and `scripts/audience_audit.py` assumed 1000; the script has
      since been corrected to `limit=200` — if you see `limit=1000`
      hardcoded anywhere, it's stale and will 400 on every sweep.
    - `cursor`: opaque cursor from previous response's `next_cursor`
    - `active`: filter by active (true) or revoked (false)
  - Response: `{ "users": [...], "next_cursor": "...|...", "has_more": true/false }`
  - User object fields: `user_id`, `email`, `name`, `phone_number`, `tags` (string[]), `tier`, `active`, `date_joined`
  - Cursor is opaque — do not parse or construct manually. Pass `next_cursor` as `cursor` until `has_more` is false.
  - Use `limit=200` to sweep a full audience in the fewest pages.
  - **Audience sizing — focus on REAL emails**: the raw list is padded with
    test/smoke/integration addresses. A "real" email has a plausible address
    (`@`, dotted domain, non-empty local part) and none of these markers:
    `example`, `fake`, `test`, `noinput`, `smoke`, `placeholder`, `dummy`,
    `invalid`, `no-reply`/`noreply`. Always report **total / real / filtered-out**
    as three numbers; never quote the raw total as the real audience. See
    `is_real()` in `scripts/audience_audit.py`.

- `POST /v3/users/lookup`
  - Expected: `200` + `user_id`, `email`, `phone_number`
  - Body: `{"email": "user@example.com"}` or `{"phone_number": "+14155552671"}`
  - Exactly one of `email` or `phone_number` must be provided.
  - Note: can auto-create user for allowed keys. All keys can look up an
    *existing* user; only some keys can create one from a fresh
    email/phone. A key that can't create returns a deterministic
    `400 {"detail":"Invalid request"}` on a never-before-seen address (no
    partial write). This was observed on `dlph_` App-Launch keys for
    Andre Agassi and Darren Cahill in July 2026 and confirmed fixed on
    2026-08-01 — if a similar 400 shows up on a create-path lookup, check
    whether it's an isolated key/clone entitlement gap before assuming a
    regression. Where creation is enabled, upsert semantics are correct:
    insert on new, same `user_id` returned on repeat lookup, no duplicates.

- `GET /v3/users/{user_id}/info`
  - Response: `{ "user_id", "info_items": [...], "total_count" }`
  - Sorted newest first.

- `POST /v3/users/{user_id}/info`
  - Body: `{"info": "...", "info_type": "..."}`
  - Response: `{ "id", "text", "created_at", "updated_at", "message_id", "source", "info_type" }`

- `PATCH /v3/users/{user_id}/info/{info_id}`
  - Update an existing info item's text or type
  - Body: `{"info": "...", "info_type": "..."}` (at least one required)
  - Preserves original `created_at`
  - Response: `{ "id", "text", "created_at", "updated_at", "message_id", "source", "info_type" }`

- `DELETE /v3/users/{user_id}/info/{info_id}`
  - Response: `{ "success": true, "message": "...", "deleted_info_id": "..." }`

Common `info_type` values:
- `GOAL`, `PREFERENCES`, `INTERESTS`, `PERSONAL_INFO`, `EXPERTISE`, `SITUATION`, `BELIEF`, `COMMUNICATION_STYLE`, `EMOTIONAL_STATE`, `RELATIONSHIP`, `WHY_DELPHI`, `HOW_DELPHI`, `JOURNAL`

- `GET /v3/users/{user_id}/flywheel` -> profile/flywheel data (undocumented — may be removed)
- `GET /v3/users/{user_id}/tier` -> tier value (`JUST ME`, `PUBLIC`, `INTERNAL`, `GROWTH`, etc.)
- `GET /v3/users/{user_id}/usage` -> quota/usage with detailed breakdown:
  - Response: `{ "period": { "start", "end", "days_remaining" }, "quota": { "messages", "voice_seconds", "video_seconds" }, "usage": { ... }, "remaining": { ... } }`
- `PATCH /v3/users/{user_id}` -> update user fields (undocumented — may change)
- `POST /v3/users/{user_id}/revoke` -> deactivate (undocumented — may change)
- `POST /v3/users/{user_id}/activate` -> reactivate (undocumented — may change)

Known quirk:
- phone validation may reject valid E.164 numbers depending on backend state.

## Tags

- `GET /v3/tags`
  - Response: `{ "tags": [{ "id", "name", "color", "created_at", "updated_at" }], "total_count" }`
  - Sorted newest first.

- `POST /v3/tags`
  - Body: `{"name": "...", "color": "blue"}` (color optional, defaults to "default")
  - Returns `409` if tag name already exists.

- `POST /v3/users/{user_id}/tags/{tag_name}`
  - Idempotent — tagging a user who already has the tag succeeds without error.

- `DELETE /v3/users/{user_id}/tags/{tag_name}`
  - Idempotent — untagging a user who doesn't have the tag succeeds without error.

## Search

- `POST /v3/search/query`
  - Semantic + keyword search across clone's knowledge base
  - Body fields:
    - `query` (string[], required): Semantic search strings (questions or topics)
    - `keywords` (string[], optional): Keyword/phrase strings for exact-match (BM25) boosting
    - `content` (string[], optional): Content descriptions to scope results to matching sources
    - `contentIds` (string[], optional): Direct content IDs to filter results to specific sources. `content_ids` (snake_case) is also accepted as an alias — same field, either casing works.
    - `limit` (number, optional): Max chunks to return (1–50, default 10)
    - `tag` (string, optional): Access tier tag (e.g. `PUBLIC`, `PREMIUM`). Defaults to broadest access.
  - How search works: `query` strings are used for semantic (meaning-based) search. `keywords` are routed through hybrid search for better exact-phrase matching via BM25. When both are provided, results are merged and deduplicated, keeping the highest-scoring passages.
  - Content scoping: Use `content` to describe the sources you want to search within (e.g. `["Series A fundraising podcast"]`). The API resolves these descriptions to matching content and restricts the chunk search to those sources. Alternatively, pass `contentIds` directly if you already know the content IDs.
  - Response: `{ "chunks": [...], "content": [...] }`
    - `chunks[].text`: The passage text
    - `chunks[].sources[]`: `{ contentId, title }` — content sources this passage belongs to
    - `chunks[].createdTime`, `chunks[].editedTime`: Timestamps
    - `content[]`: Deduplicated list of all content sources referenced by the chunks
    - `content[].contentId`, `content[].title`, `content[].contentType`, `content[].summary`, `content[].metaData`, `content[].createdTime`, `content[].editedTime`

- `POST /v3/search/content`
  - Search for content sources (documents, articles, podcasts, etc.) by title or description
  - Use this to discover available content before performing a chunk search with `/v3/search/query`
  - Body fields:
    - `query` (string[], required): Content search strings (titles, descriptions, topics)
    - `tag` (string, optional): Access tier tag (e.g. `PUBLIC`, `PREMIUM`). Defaults to broadest access.
    - `limit` (number, optional): Max content sources to return (1–50, default 10)
  - Response: `{ "content": [...] }`
    - `content[].contentId`: Unique identifier
    - `content[].title`: Title of the content
    - `content[].contentType`: Type (e.g. `podcast`, `article`, `pdf`, `video`)
    - `content[].summary`: Brief summary (may be null)
    - `content[].metaData`: Additional metadata (varies by content type)
    - `content[].createdTime`, `content[].editedTime`: Timestamps

## Agent

- `POST /v3/agent/run` — **new as of 2026-08-01**, found by diffing the live
  `GET /v3/openapi.json` against this doc; not previously covered here.
  - Runs an autonomous multi-strategy knowledge-base agent — a step up from
    `/v3/search/query`: instead of raw chunks, it fans out across passages,
    concepts, titles, and Q&A pairs, reasons over the results, and returns a
    synthesized answer plus a full reasoning trace. Live-tested successfully
    (200, ~8s for a 5s `thinking_time` budget).
  - Body fields:
    - `objective` (string, required, min length 1): the question or task
    - `thinking_time` / `thinkingTime` (number, optional, 1–120): time budget in seconds; both casings accepted
    - `schema` (string, optional): constrain the shape of the output
    - `priors` (string, optional): seed context for the agent
    - `tag` (string, optional): access-tier scoping, same convention as the search endpoints
  - Response: `{ "finalResult": "...", "steps": [{ "query", "result", "reasoning", "timestamp" }], "totalTime", "iterations", "schemaUsed" }`
  - `steps[]` is the full trace — each entry shows what the agent searched, what it found, and why, useful for debugging why an answer came out a certain way.
  - Slower and heavier than `/v3/search/query` — prefer `search/query` for simple chunk retrieval, reach for `agent/run` when you need a synthesized answer or multi-hop reasoning over the knowledge base.

## Common error codes

| HTTP | Meaning | Typical cause |
|------|---------|---------------|
| 200 | Success | Request completed normally |
| 400 | Bad Request | Malformed JSON, missing required field |
| 401 | Unauthorized | Invalid API key format or expired key |
| 403 | Forbidden | Key not active, not authorized, or not yet provisioned |
| 404 | Not Found | Invalid endpoint path or resource doesn't exist |
| 409 | Conflict | Duplicate resource (e.g. tag name already exists) |
| 422 | Unprocessable | Validation failed (e.g., invalid phone format, bad info_type) |
| 429 | Rate Limited | Too many requests — back off and retry with delay (120 req/60s) |
| 500 | Server Error | Backend failure — package a repro report with conversation_id, expected/actual |

## Safety rules for testing

- Do not create fake personal emails when the user has not provided one.
- Ask for explicit write permission before any mutating endpoint tests.
- Prefer read-only checks first, then escalate to writes only if needed.
- If clone stream fails with 500, package a repro report with conversation_id, expected/actual.
