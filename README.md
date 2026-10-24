# Delphi API Safe Skill

A production-ready, non-technical-safe skill package for testing and troubleshooting the Delphi **V3** API (conversations, streaming, voice, knowledge-base search), the Delphi **V4** Developer Platform API (contacts, knowledge-base writes, outbound messaging, webhooks, integrations), and the Delphi **web embed** (browser, no API key).

> **The web embed is a third surface, not an API.** It's authenticated by channel ID and origin. The current `www.delphi.ai/embed.js` creates a genuinely cross-origin iframe, so host-page scripts cannot reach the chat DOM — a first message is set by putting `q` on the iframe URL, and the `postMessage` bridge is SSO-only. Full capability map and debugging checklist in [`delphi-api-safe/references/embed.md`](delphi-api-safe/references/embed.md).

> **Both surfaces now have chat.** As of 2026-08-02 V4 gained conversations, SSE streaming, and stateless ask — so route by *capability*, not version. V4 additionally offers a **synchronous** send (no SSE parsing) and idempotent conversation creation. Still V3-only: voice, knowledge-base search, and the KB agent. Still V4-only: contacts/CRM, content writes, outbound SMS/email, webhooks, integrations. See [`delphi-api-safe/references/v4-endpoints.md`](delphi-api-safe/references/v4-endpoints.md) for the full map.
>
> ⚠️ **Known integration quirk** (last verified 2026-08-02): `POST /v4/conversations` is eventually consistent. Sending a message immediately can return `404 "Thread not found"`; retry on 404 with ~1s backoff (ready in ~2–6s). The stateless `ask` outage from that date was fixed and both endpoints were working when re-tested.
>
> ⚠️ **Key choice matters more than version choice.** Legacy `dsk-` keys are unscoped and work everywhere. Newer `dlph_` App-Launch keys are *scoped* and most lack `conversations:write`, so they `403` on V4 chat despite being newer — their advantage is the 10k req/min rate limit, not access breadth.

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

- Runs safe Delphi V3 checks for conversation, stream, search, agent, users, tags, and user info endpoints
- Runs safe Delphi V4 checks for profile, contacts, content, integrations, and
  webhooks by default; conversations and stateless ask are explicit opt-ins,
  while destructive endpoints (`/v4/send`, `/v4/data-deletion-requests`,
  content delete, integration publish) remain excluded from the CLI harness
- Answers web embed questions correctly for both generations — install, landing pages, styling, SSO, first-message prefill — and diagnoses embeds that render but misbehave
- Distinguishes *scope gaps* (reported as SKIP — a provisioning issue) from real failures, and labels known platform outages so the harness doesn't go red for something you can't fix
- Handles self-discovery first, then asks for missing required inputs
- Never invents sensitive/user-specific values (emails, API keys)
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
3. Constraints (redaction, timestamp inclusion, output style)

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

For knowledge base search tests (Immortal plan):

```bash
make smoke-search
```


Chat flow test:

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --account "Jim Carter" \
  --mode chat
```

Full endpoint sweep (read-only):

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode full \
  --user-email "real-user@example.com"
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
```

Knowledge base search test (Immortal plan):

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --mode chat \
  --test-search \
  --search-query "What is your background?"
```

### V4 Developer Platform tests

Read-only by default — safe to run against production:

```bash
python3 delphi-api-safe/scripts/test_delphi_v4.py --api-key "$DELPHI_API_KEY"
```

Include the metered endpoints (daily budget / token spend). Reusing the same
`--idempotency-key` across runs replays the prior reply instead of re-charging:

```bash
python3 delphi-api-safe/scripts/test_delphi_v4.py \
  --api-key "$DELPHI_API_KEY" \
  --test-generate --idempotency-key "smoke-2026-08-01" \
  --test-llm \
  --test-agents
```

`--test-agents` calls `POST /v4/agents/responses`, the OpenAI Responses-compatible
endpoint that answers as the mind with its public knowledge. Each call uses one
slot of the owner's `/v4/generate` daily budget. `GET /v4/agents/models` is free
and runs on every V4 pass.

The V4 harness deliberately does **not** implement `/v4/send`,
`/v4/data-deletion-requests`, content deletes, integration publish/push, or
secret writes — those mutate real-world state and should be run by hand.

## Interactive API Reference (browser)

A single-page interactive explorer with a **V3 / V4 toggle** in the top bar —
all 34 V3 operations and all 67 V4 operations — with a live test harness, streaming SSE
support, and curl copy/paste.

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

- **V3 / V4 toggle** in the top bar — switches the whole explorer between the two surfaces
- **V3: 34 operation cards** (Conversations, Questions, Users, Tags, User Info, Search, Agent, Clone, Voice)
- **V4: 67 operation cards** (Profile, **Conversations**, Contacts, Contact Tags, Contact Properties, Content, Generate & Send, LLM, **Agents**, Thread Sessions, Webhooks, Integrations, Data Deletion)
- **Safety banners** — high-impact state changes (send, delete, deploy, secret writes) get a red warning and an action-time confirmation; model-backed, metered, or externally visible operations get an amber warning
- **Read-only live mode by default** — GET requests can run immediately, while
  every live POST, PUT, PATCH, or DELETE requires enabling **Allow live writes**;
  risky and model-backed calls then require an additional confirmation
- **Send button** fires requests through a local CORS proxy — responses render inline. The proxy is version-agnostic, so `/api/v3/*` and `/api/v4/*` both work
- **SSE streaming** for `/v3/stream` *and* `/v4/conversations/{id}/messages/stream` — tokens appear live with a blinking cursor, token counter, and raw SSE toggle (both use the same `CloneResponse` frame contract)
- **Curl copy** on every endpoint — one click to clipboard, ready to paste in terminal
- **Auto user lookup** — enter an email in the top bar and the `user_id` auto-resolves and fills into all endpoint cards
- **Field validation** — required fields highlight red with a shake animation before sending
- **Static mode fallback** — works without the proxy (copy curl, paste output, click Format)
- **Zero dependencies** — one HTML file + one Python file, no npm/node/build step

### Contract drift check

Verify that every operation in both authenticated live OpenAPI documents has a
matching playground card:

```bash
make check-openapi
```

The check reads the key from `DELPHI_API_KEY` or the local gitignored
`smoke-config.json`. It fetches both specifications in memory and never prints
or persists the key.

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
