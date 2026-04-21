# Delphi V3 Endpoints - Tested Coverage and Notes

This file captures endpoint behavior learned from real tests.

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
    - `limit`: page size 1-1000 (default 50)
    - `cursor`: opaque cursor from previous response's `next_cursor`
    - `active`: filter by active (true) or revoked (false)
  - Response: `{ "users": [...], "next_cursor": "...|...", "has_more": true/false }`
  - User object fields: `user_id`, `email`, `name`, `phone_number`, `tags` (string[]), `tier`, `active`, `date_joined`
  - Cursor is opaque — do not parse or construct manually. Pass `next_cursor` as `cursor` until `has_more` is false.

- `POST /v3/users/lookup`
  - Expected: `200` + `user_id`, `email`, `phone_number`
  - Body: `{"email": "user@example.com"}` or `{"phone_number": "+14155552671"}`
  - Exactly one of `email` or `phone_number` must be provided.
  - Note: can auto-create user for allowed keys.

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
    - `contentIds` (string[], optional): Direct content IDs to filter results to specific sources
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
  - Response: `{ "content": [...] }`
    - `content[].contentId`: Unique identifier
    - `content[].title`: Title of the content
    - `content[].contentType`: Type (e.g. `podcast`, `article`, `pdf`, `video`)
    - `content[].summary`: Brief summary (may be null)
    - `content[].metaData`: Additional metadata (varies by content type)
    - `content[].createdTime`, `content[].editedTime`: Timestamps

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
