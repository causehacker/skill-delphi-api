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

Use the **V3 / V4 toggle** in the top bar to switch surfaces. **Both now have
chat** — V4 gained conversations and streaming on 2026-08-02, plus a
*synchronous* send that needs no SSE parsing. V3 keeps voice, knowledge-base
search, and the KB agent; V4 keeps contacts, content writes, outbound messaging,
webhooks, and integrations.

Banners on the endpoint cards tell you what's safe to press:

- **red** — changes real state (sends a message, deletes content, deploys code)
- **amber** — metered (consumes budget, tokens, or invokes the model)
- **purple** — known outage; expect a 502 until Delphi ships a fix

Two things that will otherwise look like your bug:

- `POST /v4/conversations` is **eventually consistent** — sending a message
  straight after creating one returns `404 "Thread not found"`. Wait a few
  seconds (ready in ~2–6s) and retry.
- Most `dlph_` App-Launch keys lack the `conversations:write` scope and will
  `403` on the V4 chat endpoints. Legacy `dsk-` keys work. The 403 body names
  the missing scope.

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
- `/v3/conversation/{id}/append-clone-message` (inject clone message)
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
  - `POST/PATCH/DELETE /v3/users/{user_id}/info...`
  - `GET /v3/users` (paginated user list)

## V4 endpoint coverage (`test_delphi_v4.py`)

Read-only by default — safe against production:

```bash
python3 delphi-api-safe/scripts/test_delphi_v4.py --account <name>
```

- `GET /v4/profile`, `/v4/profile/questions`, `/v4/profiles/{username}`
- opt-in conversations (`--test-conversations`): `POST /v4/conversations`, `POST /v4/conversations/{id}/messages` (synchronous send), `GET /v4/conversations/{id}/insights` — needs `conversations:write` / `insights:read`, reported as SKIP when the key lacks them
- opt-in `--test-ask`: `POST /v4/ask` — **known outage, returns 502 platform-wide** (reported 2026-08-02); the harness labels it rather than counting it as a failure
- `GET /v4/contacts`, `/v4/contacts/{id}`, `/v4/contacts/{id}/threads`
- `GET /v4/contact-tags`, `/v4/contact-properties/definitions`
- `GET /v4/content`, `/v4/content/{id}`
- `GET /v4/integrations`, `/v4/webhook-subscriptions`
- opt-in metered: `POST /v4/generate` (`--test-generate`), `POST /v4/llm/chat/completions` (`--test-llm`)

**Deliberately not implemented** — these mutate real-world state and must be run
by hand with the user watching: `POST /v4/send` (real SMS/email),
`POST /v4/data-deletion-requests` (irreversible), `DELETE /v4/content/{id}`
(knowledge loss), integration publish/push/activate (deploys live code), and
integration secret writes.

The script also reports whether the key carries the `contacts:list:pii` scope —
without it, contact rows come back with no `email` or `phone`, which looks like
missing data but is a scope difference.

## PASS/FAIL criteria

- PASS (chat): conversation 200 and stream SSE contains `data:` + `[DONE]`
- PASS (search): HTTP 200 and response contains valid `chunks` / `content` arrays
- PASS (endpoint checks): endpoint HTTP 200
- FAIL: non-200, malformed payloads, missing stream completion markers
