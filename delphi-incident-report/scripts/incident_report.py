#!/usr/bin/env python3
"""Reproduce a Delphi V3 failure and emit a redacted, support-ready incident report.

Runs the failing flow multiple times (default 3) to establish reproducibility,
captures per-attempt HTTP evidence with UTC timestamps, and emits markdown
(default) or JSON. READ-ONLY apart from creating throwaway conversations.

The API key is redacted to dsk-****<last4> everywhere, including inside
response-body previews. Email addresses in evidence are masked unless
--show-emails is passed.

Usage:
    python3 scripts/incident_report.py --api-key "$DELPHI_API_KEY"
    python3 scripts/incident_report.py --account karamo --flow voice
    python3 scripts/incident_report.py --api-key dsk-... --out out/incident.md
    python3 scripts/incident_report.py --api-key dsk-... --json
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.delphi.ai"
UA = "delphi-incident-report/1.0"  # default python-urllib UA is 403'd by Cloudflare
PREVIEW = 400


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def redact_key(key: str) -> str:
    return f"dsk-****{key[-4:]}" if len(key) > 8 else "dsk-****"


def scrub(text: str, key: str, show_emails: bool) -> str:
    """Remove the API key and (optionally) mask emails in any evidence text."""
    text = text.replace(key, redact_key(key))
    if not show_emails:
        text = re.sub(
            r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+)",
            r"\1***@\2", text)
    return text


def resolve_key(args) -> str:
    if args.api_key:
        return args.api_key
    if os.environ.get("DELPHI_API_KEY"):
        return os.environ["DELPHI_API_KEY"]
    if args.account:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "keys.json")
        if os.path.exists(path):
            accounts = json.load(open(path)).get("accounts", {})
            if args.account in accounts:
                return accounts[args.account]
            sys.exit(f"Account '{args.account}' not found in {path}.")
        sys.exit("No keys.json found for --account lookup.")
    sys.exit("Provide --api-key, set $DELPHI_API_KEY, or pass --account <name>.")


def call(method: str, path: str, key: str, payload=None, timeout: int = 45) -> dict:
    """One HTTP call. Returns {ts, method, path, status, body_preview, elapsed_ms}.
    Never raises — failures are evidence, not errors."""
    ts = now_utc()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"x-api-key": key, "Content-Type": "application/json", "User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(65536)
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read(65536)
        status = e.code
    except Exception as e:
        body = str(e).encode()
        status = 0
    try:
        preview = body.decode("utf-8", "replace")
    except Exception:
        preview = f"<{len(body)} binary bytes>"
    # Binary voice responses: don't dump PCM into the report
    if preview and not preview.lstrip()[:1] in ("{", "[", "d", "<") and any(
            ord(c) < 9 for c in preview[:64]):
        preview = f"<binary response, {len(body)} bytes>"
    return {"ts": ts, "method": method, "path": path, "status": status,
            "body_preview": preview[:PREVIEW],
            "elapsed_ms": int((time.time() - t0) * 1000)}


def run_attempt(key: str, flow: str, message: str) -> dict:
    """One end-to-end repro attempt. Returns {steps: [...], failed_step, passed}."""
    steps = [call("POST", "/v3/conversation", key, {})]
    cid = None
    if steps[-1]["status"] == 200:
        try:
            cid = json.loads(steps[-1]["body_preview"]).get("conversation_id")
        except Exception:
            cid = None
    if cid:
        endpoint = "/v3/stream" if flow == "chat" else "/v3/voice/stream"
        s = call("POST", endpoint, key, {"message": message, "conversation_id": cid})
        if flow == "chat":
            s["passed"] = s["status"] == 200 and "data:" in s["body_preview"]
        else:
            s["passed"] = s["status"] == 200
        steps.append(s)
    failed = next((s for s in steps if not s.get("passed", s["status"] == 200)), None)
    return {"steps": steps, "conversation_id": cid,
            "passed": failed is None,
            "failed_step": f"{failed['method']} {failed['path']}" if failed else None}


def build_report(key: str, flow: str, attempts: list, clone: dict, show_emails: bool) -> dict:
    fails = [a for a in attempts if not a["passed"]]
    failing_step = fails[0]["failed_step"] if fails else None
    cids = [a["conversation_id"] for a in attempts if a["conversation_id"]]
    return {
        "generated_at": now_utc(),
        "clone": {"name": clone.get("name", "<unknown>"), "slug": clone.get("slug", "")},
        "api_key": redact_key(key),
        "flow": flow,
        "reproducibility": f"{len(fails)}/{len(attempts)} attempts failed",
        "reproducible": len(fails) == len(attempts) and bool(fails),
        "failing_step": failing_step,
        "conversation_ids": cids,
        "attempts": [
            {**a, "steps": [dict(s, body_preview=scrub(s["body_preview"], key, show_emails))
                            for s in a["steps"]]}
            for a in attempts
        ],
    }


def to_markdown(rep: dict, message: str) -> str:
    stream_ep = "/v3/stream" if rep["flow"] == "chat" else "/v3/voice/stream"
    lines = [
        f"# Delphi API Incident Report — {rep['clone']['name']}",
        "",
        f"- **Generated:** {rep['generated_at']} (UTC)",
        f"- **Clone:** {rep['clone']['name']} ({rep['clone']['slug']})",
        f"- **API key:** `{rep['api_key']}`",
        f"- **Flow tested:** {rep['flow']}",
        f"- **Reproducibility:** {rep['reproducibility']}"
        + ("  — **fully reproducible**" if rep["reproducible"] else "  — intermittent, may be transient"),
        f"- **Failing step:** `{rep['failing_step'] or 'none — could not reproduce'}`",
        "",
        "## Repro steps",
        "",
        "```bash",
        'CID=$(curl -sS -X POST "https://api.delphi.ai/v3/conversation" \\',
        '  -H "x-api-key: $DELPHI_API_KEY" -H "Content-Type: application/json" \\',
        "  -d '{}' | python3 -c 'import sys,json; print(json.load(sys.stdin)[\"conversation_id\"])')",
        f'curl -i -N -X POST "https://api.delphi.ai{stream_ep}" \\',
        '  -H "x-api-key: $DELPHI_API_KEY" -H "Content-Type: application/json" \\',
        f'  -d "{{\\"message\\":\\"{message}\\",\\"conversation_id\\":\\"$CID\\"}}"',
        "```",
        "",
        "## Expected vs actual",
        "",
        "- **Expected:** HTTP 200"
        + (" with SSE `data:` chunks ending in `[DONE]`" if rep["flow"] == "chat"
           else " with binary PCM audio (24kHz 16-bit mono)"),
        "- **Actual:** see evidence below",
        "",
        "## Evidence",
        "",
        "| Attempt | Timestamp (UTC) | Endpoint | HTTP | ms | Response preview |",
        "|---------|-----------------|----------|------|----|------------------|",
    ]
    for i, a in enumerate(rep["attempts"], 1):
        for s in a["steps"]:
            prev = s["body_preview"].replace("|", "\\|").replace("\n", " ")[:120]
            lines.append(f"| {i} | {s['ts']} | `{s['method']} {s['path']}` | {s['status']} | {s['elapsed_ms']} | {prev} |")
    if rep["conversation_ids"]:
        lines += ["", "## Conversation IDs created during repro (for server-side lookup)", ""]
        lines += [f"- `{c}`" for c in rep["conversation_ids"]]
    lines += [
        "",
        "## Suspected cause",
        "",
        "_(speculation)_ Backend failure on the failing step above; all prior steps"
        " succeed with the same key, so authentication and connectivity are not the cause.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reproduce a Delphi failure and emit a redacted incident report.")
    ap.add_argument("--api-key")
    ap.add_argument("--account", help="Account name in keys.json.")
    ap.add_argument("--flow", choices=["chat", "voice"], default="chat")
    ap.add_argument("--attempts", type=int, default=3, help="Repro attempts (default 3).")
    ap.add_argument("--message", default="Please answer in one short sentence to test stream.")
    ap.add_argument("--out", help="Write the markdown report to this path (out/ is gitignored).")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of markdown.")
    ap.add_argument("--show-emails", action="store_true", help="Do not mask emails in evidence.")
    args = ap.parse_args()
    key = resolve_key(args)

    clone_step = call("GET", "/v3/clone", key)
    if clone_step["status"] == 403:
        print("403 on /v3/clone: key is not active or not authorized. This is an "
              "account/key problem, not an engineering incident — no report generated.")
        return 2
    clone = {}
    if clone_step["status"] == 200:
        try:
            raw = json.loads(clone_step["body_preview"])
            clone = raw.get("clone", raw)
        except Exception:
            pass
    print(f"clone: {clone.get('name', '<unknown>')} | running {args.attempts} "
          f"{args.flow}-flow attempts...", file=sys.stderr)

    attempts = []
    for i in range(args.attempts):
        attempts.append(run_attempt(key, args.flow, args.message))
        print(f"  attempt {i+1}: {'PASS' if attempts[-1]['passed'] else 'FAIL @ ' + str(attempts[-1]['failed_step'])}",
              file=sys.stderr)
        if i < args.attempts - 1:
            time.sleep(2)  # pace well under 120 req/60s

    rep = build_report(key, args.flow, attempts, clone, args.show_emails)

    if not any(not a["passed"] for a in attempts):
        print(f"\nAll {args.attempts} attempts PASSED — could not reproduce a failure. "
              "No incident report generated (likely transient; re-run if it recurs).")
        return 0

    output = json.dumps(rep, indent=2) if args.json else to_markdown(rep, args.message)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
        print(f"report -> {args.out}", file=sys.stderr)
    else:
        print(output)
    return 1 if rep["reproducible"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
