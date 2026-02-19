# How To Use `delphi-api-safe`

## Requirements

- Delphi API key(s)
- Clone slug(s) you want to test
- Ability to run curl or Python script

## Minimum user info the skill needs

The skill should ask for these if missing:

1. Goal (single test, matrix test, troubleshooting, incident report)
2. API key(s)
3. Clone slug(s)
4. Output constraints (redaction, table format, timezone)

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
  -d '{"slug":"jc3"}'
```

### 3) Stream reply

```bash
curl -i -N -X POST "https://api.delphi.ai/v3/stream" \
  -H "x-api-key: $DELPHI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"Please answer in one short sentence to test stream.","slug":"jc3","conversation_id":"<cid>"}'
```

## Deterministic script mode

Single test:

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --slug "jc3" \
  --account "Jim Carter"
```

Matrix test:

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --matrix-json '[{"account":"Jim Carter","api_key":"<key>","slug":"jc3"}]'
```

## PASS/FAIL criteria

- PASS: conversation returns 200 and stream emits SSE data with `[DONE]`
- FAIL: any non-200, malformed JSON, or stream missing completion marker
