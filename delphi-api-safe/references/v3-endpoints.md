# Delphi V3 Endpoints - Tested Coverage and Notes

This file captures endpoint behavior learned from real tests.

## Clone

- `GET /v3/clone`
  - Expected: `200` + JSON with clone profile
  - Response fields: `name`, `description`, `headline`, `purpose`, `tags`, `image_url`, `initial_message`
  - This is the primary way to identify which clone a key belongs to. Call it first when testing a new key.
  - If 403: key is not active or not authorized. Report this to the user immediately.

## Conversations

- `POST /v3/conversation`
  - Expected: `200` + `conversation_id`
  - Body: `{}` (empty JSON object is sufficient)
  - Note: optional `message` can be accepted but may return only `initial_message`.

- `POST /v3/stream`
  - Expected: `200` + SSE `data:` chunks + `[DONE]`
  - Body: `{"message": "...", "conversation_id": "..."}`
  - Known issue: some clones return `500 Internal Server Error` while others pass.

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

## Users

- `POST /v3/users/lookup`
  - Expected: `200` + `user_id`
  - Body: `{"email": "user@example.com"}`
  - Note: can auto-create user for allowed keys.

- `GET /v3/users/{user_id}/flywheel` -> profile/flywheel data
- `GET /v3/users/{user_id}/tier` -> tier value
- `GET /v3/users/{user_id}/usage` -> quota/usage
- `PATCH /v3/users/{user_id}` -> update user fields
- `POST /v3/users/{user_id}/revoke` -> deactivate
- `POST /v3/users/{user_id}/activate` -> reactivate

Known quirk:
- phone validation may reject valid E.164 numbers depending on backend state.

## Tags

- `GET /v3/tags`
- `POST /v3/tags`
- `POST /v3/users/{user_id}/tags/{tag_name}`
- `DELETE /v3/users/{user_id}/tags/{tag_name}`

Notes:
- Tagging/untagging is designed to be idempotent.
- Some failures return generic `Invalid request` instead of specific errors.

## User Info

- `GET /v3/users/{user_id}/info`
- `POST /v3/users/{user_id}/info`
- `DELETE /v3/users/{user_id}/info/{info_id}`

Common `info_type` values observed working:
- `WHY_DELPHI`, `HOW_DELPHI`, `INTERESTS`, `PREFERENCES`, `PERSONAL_INFO`, `GOAL`, `JOURNAL`

Common `source` values observed working:
- `MESSAGE`, `MANUAL`, `INFERENCE`, `API`

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
| 422 | Unprocessable | Validation failed (e.g., invalid phone format, bad info_type) |
| 429 | Rate Limited | Too many requests — back off and retry with delay |
| 500 | Server Error | Backend failure — package a repro report with conversation_id, expected/actual |

## Safety rules for testing

- Do not create fake personal emails when the user has not provided one.
- Ask for explicit write permission before any mutating endpoint tests.
- Prefer read-only checks first, then escalate to writes only if needed.
- If clone stream fails with 500, package a repro report with conversation_id, expected/actual.
