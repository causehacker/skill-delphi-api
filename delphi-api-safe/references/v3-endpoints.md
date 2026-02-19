# Delphi V3 Endpoints - Tested Coverage and Notes

This file captures endpoint behavior learned from real tests.

## Conversations

- `POST /v3/conversation`
  - Expected: `200` + `conversation_id`
  - Note: optional `message` can be accepted but may return only `initial_message`.

- `POST /v3/stream`
  - Expected: `200` + SSE `data:` chunks + `[DONE]`
  - Known issue: some clones return `500 Internal Server Error` while others pass.

## Users

- `POST /v3/users/lookup`
  - Expected: `200` + `user_id`
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

## Safety rules for testing

- Do not create fake personal emails when the user has not provided one.
- Ask for explicit write permission before any mutating endpoint tests.
- Prefer read-only checks first, then escalate to writes only if needed.
- If clone stream fails with 500, package a repro report with slug, conversation_id, expected/actual.
