# Intake Checklist (Non-Technical Safe Mode)

Use this checklist before running tests.

## Always ask first if missing

1. What do you want to do?
   - test one clone
   - test many clones
   - troubleshoot a failing response
   - create incident report

2. What credentials should be used?
   - API key(s), or
   - permission to use already-provided key(s)

3. Which clones?
   - exact slug(s) preferred
   - if only names provided, ask whether to auto-discover slug variants

4. Any constraints?
   - do not expose keys in output
   - redact IDs in report
   - include timestamps/timezone

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
