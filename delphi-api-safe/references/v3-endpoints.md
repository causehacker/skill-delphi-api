# Delphi V3 Endpoints - Tested Coverage and Notes

This file captures endpoint behavior learned from real tests.

## Conversations

- `POST /v3/conversation`
  - Body: `{"slug": "<optional>", "user_email": "<optional>"}`
  - `slug` is optional — omit to use account default clone.
  - Expected: `200` + `conversation_id`, `created_at`, `initial_message`

- `POST /v3/stream`
  - Body: `{"conversation_id": "<cid>", "message": "<text>", "slug": "<optional>", "file_urls": ["<optional>"]}`
  - `slug` is optional — omit to use account default clone.
  - Expected: `200` + SSE `data:` chunks + `[DONE]`
  - Known issue: some clones return `500 Internal Server Error` while others pass.
  - `file_urls` is optional; omit for text-only messages.

- `GET /v3/conversation/list?email=<user-email>`
  - Expected: `200` + `conversations` array (each: `id`, `title`, `created_at`, `medium`)
  - Note: `email` query param is required.

- `GET /v3/conversation/{conversation_id}/history?include_citations=false`
  - Expected: `200` + `messages` array (each: `id`, `text`, `sender`, `created_at`, `citations`)
  - Set `include_citations=true` to include source citations per message.

- `PUT /v3/conversation/{conversation_id}/title`
  - Body: `{"title": "<new-title>"}` (1-500 chars)
  - Expected: `200` + `id`, `title`, `updated_at`
  - Write endpoint: requires explicit permission.

- `DELETE /v3/conversation/{conversation_id}`
  - Expected: `200` + `{"status": "..."}`
  - Soft-delete (marks as hidden, not permanent).
  - Write endpoint: requires explicit permission.

## Questions

- `GET /v3/questions?type=pinned&count=5&randomize=false`
  - Expected: `200` + `questions` array (each: `id`, `index`, `question`, `pinned`, `user_edited`, `created_at`, `updated_at`)
  - `type`: `pinned` (default) | `unpinned` | `all`
  - `count`: 1-100, default 5
  - `randomize`: boolean, default false

## Users

- `POST /v3/users/lookup`
  - Body: `{"email": "<user-email>"}`
  - Expected: `200` + `user_id`, `email`
  - Note: can auto-create user for whitelisted keys.

- `GET /v3/users/{user_id}/flywheel` -> profile/flywheel data
- `GET /v3/users/{user_id}/tier` -> `{"tier": "PUBLIC|INTERNAL"}`
- `GET /v3/users/{user_id}/usage` -> period, quota, usage, remaining
- `PATCH /v3/users/{user_id}` -> update user fields
  - Body fields (all optional): `name`, `phone_number`, `sms_opt_in`, `call_opt_in`, `tier` (`PUBLIC`|`INTERNAL`)
  - Expected: `200` + `success`, `user_id`, `updated_fields`, `message`
- `POST /v3/users/{user_id}/revoke` -> deactivate (soft delete, preserves data)
- `POST /v3/users/{user_id}/activate` -> reactivate

Known quirk:
- phone validation may reject valid E.164 numbers depending on backend state.

## Tags

- `GET /v3/tags`
  - Expected: `200` + `tags` array with `id`, `name`, `color`, `created_at`, `updated_at` + `total_count`
- `POST /v3/tags`
  - Body: `{"name": "<tag-name>", "color": "<optional, default 'default'>"}`
  - Tag names must be unique per clone.
- `POST /v3/users/{user_id}/tags/{tag_name}`
- `DELETE /v3/users/{user_id}/tags/{tag_name}`

Notes:
- Tagging/untagging is designed to be idempotent.
- Some failures return generic `Invalid request` instead of specific errors.

## User Info

- `GET /v3/users/{user_id}/info`
  - Expected: `200` + `user_id`, `info_items` array, `total_count`
- `POST /v3/users/{user_id}/info`
  - Body: `{"info": "<text>", "info_type": "<type>", "source": "<source>"}`
  - **Field is `info`, not `text`.**
  - `source` defaults to `API` if omitted.
- `DELETE /v3/users/{user_id}/info/{info_id}`

Valid `info_type` values:
- `WHY_DELPHI`, `HOW_DELPHI`, `INTERESTS`, `PREFERENCES`, `PERSONAL_INFO`, `GOAL`, `JOURNAL`

Valid `source` values:
- `MESSAGE`, `MANUAL`, `INFERENCE`, `API`

## Safety rules for testing

- Do not create fake personal emails when the user has not provided one.
- Ask for explicit write permission before any mutating endpoint tests.
- Prefer read-only checks first, then escalate to writes only if needed.
- If clone stream fails with 500, package a repro report with slug, conversation_id, expected/actual.
- Conversation title update and delete are write operations; require opt-in.
