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
First, ask me only for missing required inputs (goal, API key(s), clone slug(s), output preference).
Do self-discovery for anything already present in this chat.
Do not invent any emails, keys, or slugs.
Then run the test and give me a plain-English PASS/FAIL summary plus a table.
```

## Step 3) If you want one single health check

Tell Claude:

```text
Goal: test one clone.
API key: <paste key>
Slug: <paste slug>
Output: plain English + table.
```

## Step 4) If you want a full endpoint sweep

Tell Claude:

```text
Goal: full V3 endpoint sweep.
API key: <paste key>
Slug: <paste slug>
User email for lookup: <real email>
Read-only only.
```

## Optional local one-command run

If you run locally in terminal:

1. Copy `smoke-config.example.json` to `smoke-config.json`
2. Fill only `api_key` and `slug`
3. Run:

```bash
make smoke
```

For full checks:

```bash
make smoke-full
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
