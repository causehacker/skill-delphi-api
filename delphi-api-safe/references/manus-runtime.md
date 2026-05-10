# Manus Runtime Notes for Delphi V3

Operational guidance specific to running this skill inside a Manus sandbox or any Manus task. Read this file before invoking any of the bundled scripts.

## Environment expectations

- The API key is **already provided** as `$DELPHI_API_KEY` in tasks where the user has connected their Delphi credentials. Do **not** ask Jim (or any user with a connected key) to paste it again — call `printenv DELPHI_API_KEY | head -c 4` to confirm the variable exists, then proceed.
- Always pass the key into bundled scripts via `--api-key "$DELPHI_API_KEY"` so it never appears in shell history or logs.
- Network calls go to `https://api.delphi.ai`. No proxy is required from the Manus sandbox.

## Shell timing pitfalls

The Delphi voice and stream endpoints can take **30–90 seconds** to return. Default Manus shell `timeout` (30s) will fire while the underlying process is still running, but the process is **not killed** — it keeps streaming bytes to the file or stdout. Two consequences:

1. **Always set `timeout: 90` or higher** for any `shell.exec` that triggers `/v3/voice/*`, the multi-feature demo, or `--mode full --test-voice` runs.
2. If the first `exec` times out, prefer `shell.wait` over re-running. Re-running spawns a second curl process that competes for the TTY.
3. When in doubt, redirect long-running output to a file (`> /tmp/run.log 2>&1`) and tail it. This avoids the giant SSE/PCM dump flooding the conversation context.

## Don't dump the full clone profile into context

`GET /v3/clone` returns a `purpose` field that can be **5,000+ characters** (full system prompt for the clone). This:

- Wastes context tokens on every read.
- May leak proprietary prompt engineering into chat history.

When calling clone discovery, project only what you need:

```bash
curl -sS "https://api.delphi.ai/v3/clone" -H "x-api-key: $DELPHI_API_KEY" \
  | python3 -c 'import sys,json; d=json.load(sys.stdin).get("clone",{}); \
    print(json.dumps({k:d.get(k) for k in ["name","headline","initial_message","slug","tags"]}, indent=2))'
```

The bundled `jc3_delphi_demo.py` already trims the description to 120 chars for display.

## Two scripts, two purposes

| Script | Purpose | When to use |
|---|---|---|
| `scripts/test_delphi_v3.py` | Structured JSON output, pass/fail matrix, suitable for incident docs and multi-account sweeps | Triage, smoke tests, "is this key working" checks |
| `scripts/jc3_delphi_demo.py` | Human-readable annotated walk-through of every feature with redacted key, word-wrapped responses, and saved audio files | Onboarding a user, explaining capabilities, generating sample outputs for demos |

Pick based on whether the user wants a **report** (test script) or a **tour** (demo script).

## SSE parsing pattern

When parsing `/v3/stream` output in Python, accumulate `current_token` values rather than the deprecated `text` field:

```python
tokens = []
for line in body.splitlines():
    if line.startswith("data:") and "[DONE]" not in line:
        try:
            chunk = json.loads(line[5:].strip())
            tok = chunk.get("current_token", "")
            if tok:
                tokens.append(tok)
        except Exception:
            pass
full_response = "".join(tokens)
```

`current_token` arrives as small string fragments. There is no whitespace handling needed — concatenate verbatim.

## Voice byte math

PCM 24kHz, 16-bit, mono = **48,000 bytes per second** of audio.

- `byte_count / 48000` = duration in seconds
- A typical 1–2 sentence response runs ~600KB–1.5MB
- The minimum useful threshold for "voice actually generated" is ~4,800 bytes (0.1s)

To play in the sandbox:

```bash
ffplay -f s16le -ar 24000 -ac 1 /tmp/jc3_voice_stream.bin
```

To convert to WAV for sharing:

```bash
ffmpeg -f s16le -ar 24000 -ac 1 -i /tmp/jc3_voice_stream.bin /tmp/jc3_voice_stream.wav
```

## Redaction rules in Manus context

- Always redact API keys when printing to the user: `dsk-****Xx0k` format (first 4 + `****` + last 4).
- The `redact()` function in `jc3_delphi_demo.py` is the canonical implementation — reuse it.
- Conversation IDs (`UUID4` format) are **safe to display** — they do not grant access to anything without the API key.
- User emails passed via `--user-email` are sensitive — never echo them in summary output that may end up in a shared report.

## Known passing JC3 baseline (as of last verified test)

All seven endpoint groups confirmed PASS against the JC3 clone using `$DELPHI_API_KEY`:

- Clone profile, conversation, SSE stream, multi-turn context, voice stream (~32s audio generated), TTS synthesize, tags listing.

If a future test on the same key shows any of these failing, the issue is almost certainly upstream (Delphi backend) rather than a script regression.
