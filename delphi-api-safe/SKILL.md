---
name: delphi-api-safe
description: Safely operate and troubleshoot Delphi V3 API conversations, streaming, voice, and clone endpoints for technical and non-technical users. Use when a user asks to test Delphi API keys, run pass/fail checks across accounts, generate curl commands, debug HTTP 4xx/5xx errors, or prepare incident reports. Also trigger when the user says things like "is my clone working", "test this key", "run a smoke test", "check my Delphi", "new Delphi for [name]", or shares a dsk- API key and wants to verify it. If the user pastes a Delphi API key or mentions Delphi clones in any testing or troubleshooting context, use this skill.
---

# Delphi API Safe

Run Delphi V3 API tests in a non-destructive, user-safe way. Prefer reproducible checks and clear pass/fail outputs.

## Core rules

- Use **V3 endpoints only**. Rate limit: 120 requests per 60 seconds per key.
  Supported/tested coverage includes:
  - **Clone**: `GET /v3/clone` — clone profile and identity discovery
  - **Conversations**:
    - `POST /v3/conversation` — create a conversation
    - `POST /v3/stream` — SSE text streaming (supports `file_urls`, `slug`)
    - `GET /v3/conversation/list?email=...` — list conversations for a user
    - `GET /v3/conversation/{id}/history` — message history with optional citations
    - `PUT /v3/conversation/{id}/title` — update conversation title
    - `POST /v3/conversation/{id}/append-clone-message` — inject clone message
    - `DELETE /v3/conversation/{id}` — soft-delete conversation
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
    - `DELETE /v3/users/{user_id}/info/{info_id}`
  - **Search**:
    - `POST /v3/search/query` — semantic + keyword search across clone's knowledge base
    - `POST /v3/search/content` — search content sources by title or description
- See `references/v3-endpoints.md` for request/response expectations and known quirks.
- Never invent user data (emails, API keys, clone names, webhook URLs). Users often share test output with teammates or paste it into tickets — invented data causes confusion and erodes trust.
- If a required field is missing, ask a direct question before proceeding.
- Treat API keys as sensitive secrets. Redact keys in user-visible output (e.g., `dsk-****WmQ`) or use `$DELPHI_API_KEY`. Users frequently share screens or copy chat logs, so a leaked key can be exploited within minutes. Don't echo raw keys back, even if the user provided them — the output may end up somewhere the user didn't intend.
- For non-technical users, provide copy-paste commands and plain-English interpretation.

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
