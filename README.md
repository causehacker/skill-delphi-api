# Delphi API Safe Skill

A production-ready, non-technical-safe skill package for testing and troubleshooting Delphi **V3** API conversation + streaming flows.

## What this is

This repo contains:

- `delphi-api-safe/` - the skill source (SKILL.md + references + scripts)
- `dist/delphi-api-safe.skill` - packaged skill file ready to import

## What this skill does

- Runs safe Delphi V3 checks (`/v3/conversation`, `/v3/stream`)
- Handles self-discovery first, then asks for missing required inputs
- Never invents sensitive/user-specific values (emails, API keys, slugs)
- Produces pass/fail matrices and incident-ready reports
- Uses deterministic script-based testing for repeatable results

## Install in Claude (or compatible skill loader)

1. Download `dist/delphi-api-safe.skill`
2. Import the skill in your assistant environment
3. Confirm the skill appears as `delphi-api-safe`
4. Start with: "Test this Delphi account safely" and provide required inputs

## Non-technical safe behavior

The skill always requests missing required info before acting. It will ask for:

1. Goal (single test, multi-account sweep, incident report)
2. Credentials (API key(s) or permission to use known keys)
3. Targets (clone slug(s) or names for discovery)
4. Constraints (redaction, timestamp inclusion, output style)

## Local usage (script)

Single clone:

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --api-key "$DELPHI_API_KEY" \
  --slug "jc3" \
  --account "Jim Carter"
```

Matrix mode:

```bash
python3 delphi-api-safe/scripts/test_delphi_v3.py \
  --matrix-json '[{"account":"Jim","api_key":"...","slug":"jc3"}]'
```

## Security policy

- Never commit API keys or credentials.
- Keep all examples redacted.
- If you need local secrets, use environment variables only.

See `.gitignore` and `SECURITY.md`.
