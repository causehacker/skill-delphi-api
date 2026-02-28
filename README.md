# Delphi API Safe Skill

A production-ready, non-technical-safe skill package for testing and troubleshooting Delphi **V3** API conversation + streaming flows.

## What this is

This repo contains:

| Path | Purpose |
|------|---------|
| `delphi-api-safe/` | Skill source (SKILL.md + references + scripts) |
| `dist/delphi-api-safe.skill` | Packaged skill file ready to import |
| `docs/api-reference.html` | Interactive API reference with live test harness |
| `docs/serve.py` | Local proxy server for CORS-free browser testing |
| `scripts/run_smoke.py` | Smoke test runner |

## What this skill does

- Runs safe Delphi V3 checks for conversation, stream, users, tags, and user info endpoints
- Handles self-discovery first, then asks for missing required inputs
- Never invents sensitive/user-specific values (emails, API keys, slugs)
- Produces pass/fail matrices and incident-ready reports
- Uses deterministic script-based testing for repeatable results

## Install in Claude (or compatible skill loader)

1. Download `dist/delphi-api-safe.skill`
2. Import the skill in Claude
3. Confirm the skill appears as `delphi-api-safe`
4. Follow `docs/CLAUDE-QUICKSTART.md` for copy-paste prompts

## Non-technical safe behavior

The skill always requests missing required info before acting. It will ask for:

1. Goal (single test, multi-account sweep, incident report)
2. Credentials (API key(s) or permission to use known keys)
3. Targets (clone slug(s) — optional, uses account default if omitted)
4. Constraints (redaction, timestamp inclusion, output style)

## Local usage (script)

### Easiest local option (one command)

1. Run the setup wizard:

```bash
make setup
```

It walks you through each field and writes `smoke-config.json` (git-ignored).

2. Run:

```bash
make smoke
```

For full endpoint checks:

```bash
make smoke-full
```


Chat flow test:

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --account "Jim Carter" \
  --mode chat
# Optional: add --slug "jc3" to target a specific clone
```

Full endpoint sweep (read-only):

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode full \
  --user-email "real-user@example.com"
# Optional: add --slug "jc3" to target a specific clone
```

Full endpoint sweep (includes writes, explicit opt-in):

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode full \
  --user-email "real-user@example.com" \
  --allow-write \
  --tag-name "api-test-tag" \
  --info-text "safe test note"
# Optional: add --slug "jc3" to target a specific clone
```

## Interactive API Reference (browser)

A single-page interactive explorer for all 21 V3 endpoints with a live test harness, streaming SSE support, and curl copy/paste.

### Quick start

```bash
make docs
# → opens http://localhost:8787/api-reference.html
```

Or run directly:

```bash
python3 docs/serve.py            # default port 8787
python3 docs/serve.py --port 9000  # custom port
```

### What it does

- **21 endpoint cards** organized by section (Conversations, Questions, Users, Tags, User Info)
- **Send button** fires requests through a local CORS proxy — responses render inline
- **SSE streaming** for `/v3/stream` — tokens appear live with a blinking cursor, token counter, and raw SSE toggle
- **Curl copy** on every endpoint — one click to clipboard, ready to paste in terminal
- **Auto user lookup** — enter an email in the top bar and the `user_id` auto-resolves and fills into all endpoint cards
- **Field validation** — required fields highlight red with a shake animation before sending
- **Static mode fallback** — works without the proxy (copy curl, paste output, click Format)
- **Zero dependencies** — one HTML file + one Python file, no npm/node/build step

### Stopping

```bash
make docs-stop
# or Ctrl+C in the terminal running serve.py
```

## Security policy

- Never commit API keys or credentials.
- Always redact keys in user-visible output.
- Keep all examples redacted.
- Local config storage is supported (`smoke-config.json`) and stays on your machine.
- `smoke-config.json` is gitignored.
- You can throw away stored credentials anytime by deleting `smoke-config.json`.

See `.gitignore` and `SECURITY.md`.
