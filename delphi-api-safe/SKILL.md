---
name: delphi-api-safe
description: Safely operate and troubleshoot Delphi V3 API conversations and streaming for technical and non-technical users. Use when a user asks to test Delphi API keys, verify clone slugs, run pass/fail checks across accounts, generate curl commands, debug HTTP 4xx/5xx errors, or prepare incident reports. Always perform self-discovery first, then ask for any missing required inputs instead of inventing values.
---

# Delphi API Safe

Run Delphi V3 API tests in a non-destructive, user-safe way. Prefer reproducible checks and clear pass/fail outputs.

## Core rules

- Use **V3 endpoints only**. Supported/tested coverage includes:
  - `POST /v3/conversation`
  - `POST /v3/stream`
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
- Never invent user data (emails, API keys, slugs, clone names, webhook URLs).
- If a required field is missing, ask a direct question before proceeding.
- Treat API keys as sensitive secrets.
- ALWAYS redact keys in user-visible output. Show only masked form (example: `dsk-****WmQ`) or use `$DELPHI_API_KEY`.
- Never echo raw keys back to the user, even if the key was user-provided, unless the user explicitly asks for full key replay.
- For non-technical users, always provide copy-paste commands and plain-English interpretation.

## Required user inputs

Collect the minimum needed for the requested task:

1. **Goal**: what they want to test (single clone, full account sweep, incident report, etc.)
2. **Credential source**:
   - API key(s), or
   - permission to discover from their provided files/context
3. **Target clone(s)**:
   - exact slug(s), or
   - clone names if discovery is requested
4. **Test prompt** (optional): use a default only if user does not care

If any required input is missing, ask concise follow-ups. See `references/intake-checklist.md`.

## Guided intake (wizard mode)

When starting a new Delphi API task, ask this exact short intake first if anything required is missing:

1. What do you want to do?
   - test one clone
   - test multiple clones
   - troubleshoot a failing clone
   - generate incident report
2. What API key(s) should I use?
   - paste key(s), or
   - approve using keys already shared in this chat/context
3. Which clone slug(s) should I test?
4. Any output preferences?
   - redact IDs/keys
   - markdown table
   - include timestamps/timezone

If all four are already present, do not ask again.

## Workflow

1. **Confirm scope**
   - Single clone test, or multi-account matrix.
2. **Self-discover what you can**
   - Reuse provided slugs/keys from user message or known workspace docs.
   - Do not guess unknown values.
3. **Run baseline API checks**
   - `conversation` check first.
   - `stream` check second with returned `conversation_id`.
4. **Classify results**
   - PASS: conversation 200 + stream returns SSE (`data:`) and completion marker (`[DONE]`).
   - FAIL: any non-200, empty stream, missing done marker, invalid JSON payload.
5. **Report clearly**
   - Provide a grid with Account, Slug, Conversation, Stream, Overall, Note.
   - Include one known-good sample and one failure sample when relevant.
6. **Escalation package**
   - Include repro steps, expected/actual, conversation IDs, and timestamps.

## Standard commands

### Create conversation

```bash
curl -sS -X POST "https://api.delphi.ai/v3/conversation" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"slug":"<slug>"}'
```

### Stream message

```bash
curl -i -N -X POST "https://api.delphi.ai/v3/stream" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"<prompt>","slug":"<slug>","conversation_id":"<cid>"}'
```

### One-liner test (single clone)

```bash
CID=$(curl -sS -X POST "https://api.delphi.ai/v3/conversation" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"slug":"<slug>"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["conversation_id"])') && \
echo "CID=$CID" && \
curl -i -N -X POST "https://api.delphi.ai/v3/stream" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"<prompt>\",\"slug\":\"<slug>\",\"conversation_id\":\"$CID\"}"
```

## Non-technical UX rules

- Explain each result in one line: "Create worked, stream failed with 500".
- Always redact secrets in all summaries, tables, and examples.
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
python3 scripts/test_delphi_v3.py --api-key "$DELPHI_API_KEY" --slug "<slug>" --mode chat
```

Run full mode (users/tags/info included):

```bash
python3 scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --slug "<slug>" \
  --mode full \
  --user-email "<real-user-email>"
```

Enable write endpoint tests only with explicit consent:

```bash
python3 scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --slug "<slug>" \
  --mode full \
  --user-email "<real-user-email>" \
  --allow-write \
  --tag-name "<tag-name>" \
  --info-text "<safe-test-note>"
```

The script prints structured JSON suitable for incident docs.
