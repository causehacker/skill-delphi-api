# How To Use `delphi-api-safe`

## Requirements

- Delphi API key(s)
- Python 3.8+ (for scripts and local proxy)

## Interactive API Reference (recommended for exploration)

The fastest way to explore and test the API:

```bash
make docs
# → http://localhost:8787/api-reference.html
```

Enter your API key and optionally a user email in the top bar. Open any endpoint card and click **Send** to fire a live request. The `/v3/stream` endpoint streams tokens in real-time with a blinking cursor. See `README.md` for full details.

## CLI usage

## Minimum info the skill needs (when using Claude)

The skill should ask for these if missing:

1. Goal (single test, matrix test, troubleshooting, incident report)
2. API key(s)
3. Output constraints (redaction, table format, timezone)

## Example command flow

### 1) Set key

```bash
export DELPHI_API_KEY="<your-key>"
```

### 2) Create conversation

```bash
curl -sS -X POST "https://api.delphi.ai/v3/conversation" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 3) Stream reply

```bash
curl -i -N -X POST "https://api.delphi.ai/v3/stream" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"Please answer in one short sentence to test stream.","conversation_id":"<cid>"}'
```

## Deterministic script mode

### Chat flow only

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --account "Jim Carter" \
  --mode chat
```

### Full endpoint checks (read-only + chat)

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode full \
  --user-email "real-user@example.com"
```

### Full endpoint checks with writes (explicit opt-in)

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode full \
  --user-email "real-user@example.com" \
  --allow-write \
  --tag-name "api-test-tag" \
  --info-text "safe test note"
```

### Knowledge base search (Immortal plan)

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode chat \
  --test-search \
  --search-query "What is your background?"
```

Or via make:

```bash
make smoke-search
```

## Endpoint coverage in full mode

- `/v3/conversation`, `/v3/stream`
- `/v3/clone`
- `/v3/voice/stream` (requires clone with voice configured)
- `/v3/voice/synthesize` (text-to-speech, no conversation needed)
- `/v3/conversation/list` (requires `--user-email`)
- `/v3/conversation/{id}/history`
- `/v3/questions`
- `/v3/users/lookup`
- `/v3/users/{user_id}/flywheel`
- `/v3/users/{user_id}/tier`
- `/v3/users/{user_id}/usage`
- `/v3/tags`
- `/v3/search/query` (semantic + keyword knowledge base search, Immortal plan)
- `/v3/search/content` (content source discovery, Immortal plan)
- plus write endpoints when `--allow-write` is provided:
  - `PUT /v3/conversation/{id}/title`
  - `DELETE /v3/conversation/{id}`
  - `PATCH /v3/users/{user_id}`
  - `POST /v3/users/{user_id}/revoke`
  - `POST /v3/users/{user_id}/activate`
  - `POST /v3/tags`
  - `POST/DELETE /v3/users/{user_id}/tags/{tag_name}`
  - `POST/DELETE /v3/users/{user_id}/info...`

## PASS/FAIL criteria

- PASS (chat): conversation 200 and stream SSE contains `data:` + `[DONE]`
- PASS (search): HTTP 200 and response contains valid `chunks` / `content` arrays
- PASS (endpoint checks): endpoint HTTP 200
- FAIL: non-200, malformed payloads, missing stream completion markers
