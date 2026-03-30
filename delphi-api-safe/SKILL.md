---
name: delphi-api-safe
description: Safely operate and troubleshoot Delphi V3 API conversations, streaming, voice, and clone endpoints for technical and non-technical users. Use when a user asks to test Delphi API keys, run pass/fail checks across accounts, generate curl commands, debug HTTP 4xx/5xx errors, or prepare incident reports. Also trigger when the user says things like "is my clone working", "test this key", "run a smoke test", "check my Delphi", "new Delphi for [name]", or shares a dsk- API key and wants to verify it. If the user pastes a Delphi API key or mentions Delphi clones in any testing or troubleshooting context, use this skill.
---

# Delphi API Safe

Run Delphi V3 API tests in a non-destructive, user-safe way. Prefer reproducible checks and clear pass/fail outputs.

## Core rules

- Use **V3 endpoints only**. Supported/tested coverage includes:
  - `GET /v3/clone` — clone profile and identity discovery
  - `POST /v3/conversation` — create a conversation
  - `POST /v3/stream` — SSE text streaming
  - `POST /v3/voice/stream` — binary PCM audio streaming (24kHz, 16-bit, mono)
  - `POST /v3/voice/synthesize` — text-to-speech (batch base64 or streaming PCM)
  - `POST /v3/users/lookup`
  - `GET /v3/users/{user_id}/flywheel`
  - `GET /v3/users/{user_id}/tier`
  - `GET /v3/users/{user_id}/usage`
  - `PATCH /v3/users/{user_id}`
  - `POST /v3/users/{user_id}/revoke`
  - `POST /v3/users/{user_id}/activate`
  - `GET /v3/tags`
  - `POST /v3/tags`
  - `POST /v3/users/{user_id}/tags/{tag_name}`
  - `DELETE /v3/users/{user_id}/tags/{tag_name}`
  - `GET /v3/users/{user_id}/info`
  - `POST /v3/users/{user_id}/info`
  - `DELETE /v3/users/{user_id}/info/{info_id}`
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
