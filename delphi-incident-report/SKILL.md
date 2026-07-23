---
name: delphi-incident-report
description: Reproduce a Delphi V3 API failure and generate a redacted, ready-to-send incident report for Delphi support. Use when a clone is failing ("500 on stream", "my clone stopped responding", "voice is broken", "API is erroring"), when the user asks for an incident report, repro steps, or "something to send to Delphi support", or when a smoke test shows a persistent FAIL that needs escalation. Runs the repro multiple times to establish reproducibility before claiming a bug.
---

# Delphi Incident Report

Turn "my clone is broken" into a support-ready incident report: verified repro,
timestamps, HTTP evidence, and redacted identifiers — in one command. Never send
Delphi support a report based on a single failed request.

## Rules

- **One 500 is not an incident.** `conversation/list` (and occasionally other
  endpoints) throws intermittent 500s. The script runs the failing flow 3 times;
  only a failure on every attempt is "reproducible". Report the actual N/M count.
- **403 on everything is not an incident either** — it means the key is not
  active/authorized. Report that to the user instead of generating a report.
- **Redact always**: API key as `dsk-****<last4>` everywhere, including inside
  response-body previews. Real user emails appearing in evidence get masked to
  `j***@domain.com` unless the user explicitly wants them included.
- The report states **observed** facts (status codes, timestamps, previews) and
  keeps speculation to a single clearly-labeled "Suspected cause" line.

## Workflow

1. **Identify the failing flow.** Default is the chat flow
   (`clone → conversation → stream`); `--flow voice` covers
   `conversation → voice/stream`. If the user pasted an error, match the flow to it.
2. **Run the script** (read-only; it only creates throwaway conversations):

```bash
# Chat-flow incident (default), 3 attempts, markdown to stdout:
python3 delphi-incident-report/scripts/incident_report.py --api-key "$DELPHI_API_KEY"

# Voice flow, write report to a local file (out/ is gitignored):
python3 delphi-incident-report/scripts/incident_report.py \
  --api-key "$DELPHI_API_KEY" --flow voice --out out/incident.md

# Named account from keys.json, machine-readable:
python3 delphi-incident-report/scripts/incident_report.py --account karamo --json
```

3. **Interpret for the user in one line each**, e.g. "Conversation creation
   works; the stream endpoint failed 3/3 times with HTTP 500 — this is
   reproducible and worth sending to Delphi."
4. **If everything passed**, say so — "could not reproduce; likely transient" —
   and do not produce an incident report.
5. Reports containing conversation IDs or emails go to `out/` (gitignored) or
   into chat — never into tracked files.

## Report contents (what the script emits)

- Summary line: clone name, failing endpoint, N/M reproducibility, first-seen timestamp (UTC)
- Environment: base URL, redacted key, clone name/slug
- Numbered repro steps as curl commands using `$DELPHI_API_KEY`
- Evidence table per attempt: timestamp, endpoint, HTTP status, response preview (≤400 chars, redacted)
- `conversation_id`s created during repro (support can look them up server-side)
- Expected vs actual, one line each
- Suspected cause (single line, labeled as speculation)

## Escalation

If the failure is intermittent (some attempts pass), report the pattern
("2/3 failed") and recommend re-running before escalating. If the key itself is
dead (403 across the board), route to account support, not engineering.
