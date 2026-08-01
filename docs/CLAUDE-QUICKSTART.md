# Claude Quickstart (Non-Technical)

This is the easiest way to use the Delphi API skill in Claude.

## Step 1) Import the skill

Use this file:

- `dist/delphi-api-safe.skill`

## Step 2) Start with this exact prompt in Claude

Copy and paste:

```text
Use the delphi-api-safe skill.
Run in safe non-technical mode.
First, ask me only for missing required inputs (goal, API key(s), output preference).
Do self-discovery for anything already present in this chat.
Do not invent any emails or keys.
Then run the test and give me a plain-English PASS/FAIL summary plus a table.
```

## Step 3) If you want one single health check

Tell Claude:

```text
Goal: test one clone.
API key: <paste key>
Output: plain English + table.
```

## Step 4) If you want to search the knowledge base

Tell Claude:

```text
Goal: search my clone's knowledge base.
API key: <paste key>
Search for: fundraising advice
```

## Step 5) If you want a full endpoint sweep

Tell Claude:

```text
Goal: full V3 endpoint sweep.
API key: <paste key>
User email for lookup: <real email>
Read-only only.
```

## Step 6) V4 Developer Platform (contacts, content, webhooks)

V4 is a **separate surface** from V3 — it has no chat, streaming, voice, or
search. Reach for it when you want to manage contacts, write to the knowledge
base, or wire up webhooks.

```text
Goal: V4 read-only sweep.
API key: <paste key>
Read-only only.
```

Useful V4 asks:

```text
Add this Q&A pair to my knowledge base: "<question>" / "<answer>"
```

```text
How many contacts do I have, and which ones haven't interacted in 90 days?
```

Claude will confirm before anything that changes real state — V4 can send a real
SMS or email (`/v4/send`), delete knowledge (`DELETE /v4/content/{id}`), or
deploy live code (integrations). Those always need your explicit go-ahead.

## Optional local one-command run

If you run locally in terminal:

1. Run the setup wizard to create your config:

```bash
make setup
```

2. Run:

```bash
make smoke
```

For full checks:

```bash
make smoke-full
```

For knowledge base search:

```bash
make smoke-search
```

## Important safety notes

- The skill should ALWAYS redact keys in user-visible responses.
- Never paste real keys into public chats or GitHub issues.
- Never invent a user email - use a real one provided by the user.
- Keep `allow_write` off unless explicitly approved.

## Key storage and deletion

- If you use local config (`smoke-config.json`), the key is stored only on your machine.
- `smoke-config.json` is gitignored to prevent accidental commits.
- To throw away credentials, delete `smoke-config.json` (or clear its `api_key` value).
