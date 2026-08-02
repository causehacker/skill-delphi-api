#!/usr/bin/env python3
"""Delphi V4 (Developer Platform API) tester — READ-ONLY by default.

V4 is a separate surface from V3, not a replacement: it has no chat, stream,
voice, or search. This script exercises the safe read surface and, only when
explicitly asked, the two metered generation endpoints.

DELIBERATELY NOT IMPLEMENTED — these mutate real-world state and must be run by
hand with the user watching:
    POST   /v4/send                              sends a real SMS/email
    POST   /v4/data-deletion-requests            irreversible data deletion
    DELETE /v4/content/{id}                      real knowledge-base loss
    POST   /v4/integrations/{id}/publish|push    deploys live code
    PUT    /v4/integrations/{id}/secrets/{name}  writes a credential
    POST   /v4/notify-owner                      notifies the owner for real

Usage:
    python3 scripts/test_delphi_v4.py --api-key "$DELPHI_API_KEY"
    python3 scripts/test_delphi_v4.py --account jim_carter          # from keys.json
    python3 scripts/test_delphi_v4.py --api-key ... --test-generate # metered
    python3 scripts/test_delphi_v4.py --api-key ... --test-llm      # token spend
"""

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, Optional, Tuple

BASE = "https://api.delphi.ai/v4"


def run(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return (p.stdout or "") + ("" if p.returncode == 0 else ("\n" + (p.stderr or "")))


def http_json(method: str, path: str, api_key: str, payload: Optional[dict] = None,
              max_time: int = 45) -> Tuple[str, Any, str]:
    """Returns (status, parsed_json_or_None, raw_body_truncated)."""
    data = f" -d {shlex.quote(json.dumps(payload))}" if payload is not None else ""
    cmd = (
        f"curl -sS --max-time {max_time} -w '\\nHTTP_STATUS:%{{http_code}}' -X {method} "
        f"'{BASE}{path}' -H 'x-api-key: {api_key}' -H 'Content-Type: application/json'{data}"
    )
    raw = run(cmd)
    if "HTTP_STATUS:" not in raw:
        return "000", None, raw.strip()[:200]
    body, status = raw.rsplit("HTTP_STATUS:", 1)
    body = body.strip()
    try:
        parsed = json.loads(body)
    except Exception:
        parsed = None
    return status.strip(), parsed, body[:200]


def err_note(status: str, parsed: Any, raw: str) -> str:
    """V4 errors are {"type","code","message"} — surface code+message, not V3's `detail`."""
    if isinstance(parsed, dict):
        if "code" in parsed or "message" in parsed:
            return f"http {status} {parsed.get('code','')}: {parsed.get('message','')}".strip()
        if "detail" in parsed:  # defensive — shouldn't happen on v4
            return f"http {status} {parsed['detail']}"
    return f"http {status} {raw}".strip()


def unwrap(parsed: Any, *nested: str) -> Any:
    """V4 wraps payloads in `data`; some endpoints nest one level deeper."""
    if not isinstance(parsed, dict) or "data" not in parsed:
        return None
    d = parsed["data"]
    for key in nested:
        if isinstance(d, dict) and key in d:
            d = d[key]
    return d


def check_get(label: str, path: str, api_key: str, *, nested: tuple = (),
              want: str = "any") -> Tuple[Dict[str, Any], Any]:
    """Generic read check. Returns (result, unwrapped_payload). want: 'list'|'dict'|'any'."""
    status, parsed, raw = http_json("GET", path, api_key)
    payload = unwrap(parsed, *nested)
    ok = status == "200" and payload is not None
    if ok and want == "list":
        ok = isinstance(payload, list)
    elif ok and want == "dict":
        ok = isinstance(payload, dict)
    out: Dict[str, Any] = {
        label: "PASS" if ok else "FAIL",
        f"{label}_http": status,
        "note": "" if ok else err_note(status, parsed, raw),
    }
    if isinstance(payload, list):
        out["count"] = len(payload)
    if isinstance(parsed, dict) and "nextCursor" in parsed:
        out["has_next_page"] = parsed["nextCursor"] is not None
    return out, payload


def test_profile(api_key: str) -> Dict[str, Any]:
    """Identity discovery — the V4 analogue of GET /v3/clone."""
    res, payload = check_get("profile", "/profile", api_key, want="dict")
    if isinstance(payload, dict):
        user = payload.get("user") or {}
        res["owner_name"] = user.get("name")
        res["username"] = user.get("username")
        res["is_verified"] = payload.get("isVerified")
    return res


def test_contacts(api_key: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Cohort list. Also reports whether the key carries the PII scope."""
    res, rows = check_get("contacts", "/contacts?limit=5", api_key, want="list")
    contact_id = None
    if isinstance(rows, list) and rows:
        contact_id = rows[0].get("id")
        # A key without contacts:list:pii gets rows with no email/phone at all.
        res["pii_scope"] = any("email" in r for r in rows)
        res["sample_fields"] = sorted(rows[0].keys())
    return res, contact_id


def test_contact_detail(api_key: str, contact_id: str) -> Dict[str, Any]:
    res, payload = check_get("contact_detail", f"/contacts/{contact_id}", api_key, want="dict")
    if isinstance(payload, dict):
        res["access_tier"] = payload.get("accessTier")
        res["interactions"] = payload.get("totalInteractionCount")
    return res


def test_contact_threads(api_key: str, contact_id: str) -> Dict[str, Any]:
    res, rows = check_get("contact_threads", f"/contacts/{contact_id}/threads?limit=3",
                          api_key, want="list")
    if isinstance(rows, list) and rows:
        res["has_summary"] = bool(rows[0].get("summary"))
        res["channel_types"] = sorted({r.get("channelType") for r in rows if r.get("channelType")})
    return res


def test_content(api_key: str) -> Tuple[Dict[str, Any], Optional[str]]:
    res, rows = check_get("content", "/content?limit=5", api_key, want="list")
    content_id = None
    if isinstance(rows, list) and rows:
        content_id = rows[0].get("id")
        res["types"] = sorted({r.get("type") for r in rows if r.get("type")})
        res["statuses"] = sorted({r.get("status") for r in rows if r.get("status")})
    return res, content_id


def test_conversations(api_key: str, message: str) -> Dict[str, Any]:
    """Exercise the v4 conversational surface added 2026-08-02.

    Gated on `conversations:write` — most dlph_ App-Launch keys lack it and get
    403 here while legacy dsk- keys succeed. A 403 is reported as a scope gap,
    not a generic failure, because the fix is provisioning rather than code.
    """
    out: Dict[str, Any] = {}
    st, parsed, raw = http_json("POST", "/conversations", api_key, {})
    payload = unwrap(parsed)
    cid = payload.get("conversationId") if isinstance(payload, dict) else None
    has_scope = st == "200"
    out["conversations"] = "PASS" if cid else ("SKIP" if st == "403" else "FAIL")
    out["conversations_http"] = st
    out["conversations_write_scope"] = has_scope
    out["conversation_id"] = cid
    if st == "403":
        out["note"] = "key lacks `conversations:write` — provisioning gap, not a code fault"
        return out
    if not cid:
        out["note"] = err_note(st, parsed, raw)
        return out

    # Synchronous send — the main ergonomic win over v3 (no SSE parsing).
    #
    # POST /v4/conversations is EVENTUALLY CONSISTENT: it returns a
    # conversationId before the underlying thread exists, so an immediate send
    # gets 404 {"code":"resource_not_found","message":"Thread not found"}.
    # Measured 2026-08-02: the thread became ready after ~2-6s. Retry on 404
    # rather than sleeping a fixed amount.
    attempts = 0
    for attempt in range(6):
        attempts = attempt + 1
        st2, parsed2, raw2 = http_json("POST", f"/conversations/{cid}/messages", api_key,
                                       {"text": message}, max_time=120)
        if st2 != "404":
            break
        time.sleep(1.0)
    p2 = unwrap(parsed2)
    ok2 = st2 == "200" and isinstance(p2, dict) and bool(p2.get("text"))
    out["messages_sync"] = "PASS" if ok2 else "FAIL"
    out["messages_sync_http"] = st2
    out["messages_sync_attempts"] = attempts
    if attempts > 1:
        out["messages_sync_note"] = (f"thread not ready on first try — succeeded on attempt {attempts} "
                                     "(POST /conversations is eventually consistent)")
    if isinstance(p2, dict):
        out["reply_preview"] = (p2.get("text") or "")[:160]
        out["citations"] = len(p2.get("citations") or [])
    if not ok2:
        out["messages_sync_note"] = err_note(st2, parsed2, raw2)

    # insights — async, so an empty list is a PASS
    st3, parsed3, raw3 = http_json("GET", f"/conversations/{cid}/insights?limit=5", api_key)
    ins = unwrap(parsed3)
    ok3 = st3 == "200" and isinstance(ins, list)
    out["insights"] = "PASS" if ok3 else ("SKIP" if st3 == "403" else "FAIL")
    out["insights_http"] = st3
    out["insight_count"] = len(ins) if isinstance(ins, list) else 0
    if st3 == "403":
        out["insights_note"] = "key lacks `insights:read`"
    return out


def test_ask(api_key: str, question: str) -> Dict[str, Any]:
    """POST /v4/ask — stateless Q&A.

    KNOWN OUTAGE (reported 2026-08-02): 502 dependency_failure for all callers on
    both v3 and v4. Not a scope problem — that returns 403 naming the scope.
    """
    st, parsed, raw = http_json("POST", "/ask", api_key, {"question": question}, max_time=90)
    payload = unwrap(parsed)
    answer = payload.get("answer") or payload.get("text") if isinstance(payload, dict) else None
    ok = st == "200" and bool(answer)
    note = ""
    if not ok:
        note = ("KNOWN OUTAGE: /v4/ask returns 502 platform-wide (reported 2026-08-02) "
                "— not a problem with this key" if st == "502" else err_note(st, parsed, raw))
    return {
        "ask": "PASS" if ok else "FAIL",
        "ask_http": st,
        "known_outage": st == "502",
        "answer_preview": (answer or "")[:160],
        "note": note,
    }


def test_generate(api_key: str, prompt: str, idem: Optional[str]) -> Dict[str, Any]:
    """METERED — reserves one slot from the owner's daily budget (unless replayed)."""
    body: Dict[str, Any] = {"prompt": prompt}
    if idem:
        body["idempotencyKey"] = idem
    status, parsed, raw = http_json("POST", "/generate", api_key, body, max_time=90)
    payload = unwrap(parsed)
    ok = status == "200" and isinstance(payload, dict) and bool(payload.get("text"))
    res = {
        "generate": "PASS" if ok else "FAIL",
        "generate_http": status,
        "note": "" if ok else err_note(status, parsed, raw),
    }
    if isinstance(payload, dict):
        res["text_preview"] = (payload.get("text") or "")[:160]
        res["budget_remaining"] = payload.get("budgetRemaining")
        res["replayed"] = payload.get("replayed")
    if status == "429":
        res["note"] = "daily generation budget exhausted (429)"
    elif status == "503":
        res["note"] = "budget could not be enforced — fails closed, nothing generated (503)"
    return res


def test_llm(api_key: str, prompt: str) -> Dict[str, Any]:
    """Token spend. NOTE: no `data` envelope — raw OpenAI shape."""
    status, parsed, raw = http_json(
        "POST", "/llm/chat/completions", api_key,
        {"messages": [{"role": "user", "content": prompt}]}, max_time=90,
    )
    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    ok = status == "200" and isinstance(choices, list) and bool(choices)
    res = {
        "llm": "PASS" if ok else "FAIL",
        "llm_http": status,
        "note": "" if ok else err_note(status, parsed, raw),
    }
    if ok:
        msg = choices[0].get("message") or {}
        res["model"] = parsed.get("model")
        res["content_preview"] = (msg.get("content") or "")[:160]
        res["usage"] = parsed.get("usage")
    if status == "403":
        res["note"] = "key lacks the `llm` scope (403)"
    return res


def resolve_key(args) -> str:
    if args.api_key:
        return args.api_key
    if os.environ.get("DELPHI_API_KEY"):
        return os.environ["DELPHI_API_KEY"]
    if args.account:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        for path in (os.path.join(root, "keys.json"),
                     os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "keys.json")):
            if os.path.exists(path):
                accounts = json.load(open(path)).get("accounts", {})
                if args.account in accounts:
                    return accounts[args.account]
                sys.exit(f"Account '{args.account}' not found in {path}.")
        sys.exit("No keys.json found for --account lookup.")
    sys.exit("Provide --api-key, set $DELPHI_API_KEY, or pass --account <name>.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Delphi V4 Developer Platform tester (read-only by default)")
    ap.add_argument("--api-key")
    ap.add_argument("--account", help="Account name in keys.json (e.g. jim_carter).")
    ap.add_argument("--username", help="Public username for GET /v4/profiles/{username}.")
    ap.add_argument("--test-generate", action="store_true",
                    help="Include POST /v4/generate — METERED against the owner's daily budget.")
    ap.add_argument("--generate-prompt", default="Reply with one short sentence to confirm generation works.")
    ap.add_argument("--idempotency-key", help="Reuse across runs to replay instead of spending budget.")
    ap.add_argument("--test-llm", action="store_true",
                    help="Include POST /v4/llm/chat/completions — costs tokens.")
    ap.add_argument("--llm-prompt", default="Reply with exactly: OK")
    ap.add_argument("--test-conversations", action="store_true",
                    help="Include the v4 conversational surface (create + synchronous send + "
                         "insights). Needs `conversations:write`; invokes the model.")
    ap.add_argument("--conversation-message", default="Reply in one short sentence.")
    ap.add_argument("--test-ask", action="store_true",
                    help="Include POST /v4/ask (KNOWN OUTAGE — 502 platform-wide as of 2026-08-02).")
    ap.add_argument("--ask-question", default="What is your background?")
    args = ap.parse_args()
    key = resolve_key(args)

    out: Dict[str, Any] = {"api": "v4", "base": BASE}

    out["profile"] = test_profile(key)
    out["profile_questions"], _ = check_get("profile_questions", "/profile/questions",
                                            key, nested=("questions",), want="list")

    username = args.username or out["profile"].get("username")
    if username:
        out["profile_by_username"], _ = check_get(
            "profile_by_username", f"/profiles/{username}", key, want="dict")

    out["contacts"], contact_id = test_contacts(key)
    if contact_id:
        out["contact_detail"] = test_contact_detail(key, contact_id)
        out["contact_threads"] = test_contact_threads(key, contact_id)

    out["contact_tags"], _ = check_get("contact_tags", "/contact-tags", key, want="list")
    out["contact_property_defs"], _ = check_get(
        "contact_property_defs", "/contact-properties/definitions", key, want="list")

    out["content"], content_id = test_content(key)
    if content_id:
        out["content_detail"], _ = check_get(
            "content_detail", f"/content/{content_id}", key, want="dict")

    out["integrations"], _ = check_get("integrations", "/integrations?limit=5", key, want="list")
    out["webhook_subscriptions"], _ = check_get(
        "webhook_subscriptions", "/webhook-subscriptions", key,
        nested=("subscriptions",), want="list")

    if args.test_conversations:
        out["conversations"] = test_conversations(key, args.conversation_message)
    if args.test_ask:
        out["ask"] = test_ask(key, args.ask_question)
    if args.test_generate:
        out["generate"] = test_generate(key, args.generate_prompt, args.idempotency_key)
    if args.test_llm:
        out["llm"] = test_llm(key, args.llm_prompt)

    # Roll-up. Two categories are deliberately NOT counted as failures:
    #   SKIP          — the key lacks a scope; a provisioning gap, not a fault
    #   known_outage  — a documented platform-side bug (e.g. /ask 502)
    # Counting either would make the harness go red for something the caller
    # cannot fix, which trains people to ignore the result.
    checks, skipped, outages = [], [], []
    for name, v in out.items():
        if not isinstance(v, dict):
            continue
        if v.get("known_outage"):
            outages.append(name)
            continue
        for label, verdict in v.items():
            if verdict == "SKIP":
                skipped.append(f"{name}.{label}" if label != name else name)
            elif verdict in ("PASS", "FAIL") and (label == name or label in
                    ("messages_sync", "insights", "conversations")):
                checks.append((f"{name}.{label}" if label != name else name, verdict))

    failed = [n for n, v in checks if v == "FAIL"]
    out["summary"] = {
        "overall": "PASS" if checks and not failed else "FAIL",
        "checks": len(checks),
        "passed": sum(1 for _, v in checks if v == "PASS"),
        "failed": failed,
        "skipped_missing_scope": skipped,
        "known_outages": outages,
    }

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
