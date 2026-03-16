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
