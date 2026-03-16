# Intake Checklist (Non-Technical Safe Mode)

Use this checklist before running tests — but only ask for what's actually missing.

## Required inputs (ask only if missing)

1. What do you want to do?
   - test one clone
   - test many clones
   - troubleshoot a failing response
   - create incident report

2. What credentials should be used?
   - API key(s), or
   - permission to use already-provided key(s)

3. Any constraints?
   - do not expose keys in output
   - redact IDs in report
   - include timestamps/timezone

## Clone identity is auto-discovered

Use `GET /v3/clone` with the provided key to discover which clone the key belongs to.
Do not ask the user for a clone name or identifier — the API tells you.

## Never assume

- email addresses
- API keys
- account ownership
- production vs staging environment
- desired prompt wording

## Safe default prompt

If user does not care about prompt content, use:

`Please answer in one short sentence to test stream.`

## Result language template

- PASS: `Conversation and stream both succeeded.`
- FAIL: `Conversation succeeded, stream failed with HTTP <code>.`
- UNKNOWN: `Could not complete test due to missing required input: <field>.`
