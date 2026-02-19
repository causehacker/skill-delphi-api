# Security

## Hard rule

Never commit API keys, access tokens, cookies, session IDs, or private credentials to this repository.

## Required practices

- Use environment variables for secrets.
- Keep test outputs scrubbed/redacted.
- Do not include real keys in docs, examples, or screenshots.
- Rotate any key immediately if accidental exposure occurs.

## Recommended env vars

- `DELPHI_API_KEY`

## Pre-push checklist

- [ ] `git diff` contains no credential-looking strings
- [ ] No `dsk-`, `sk-`, `ghp_`, `gho_`, `Bearer ` values in committed files
- [ ] Example payloads use placeholders only
