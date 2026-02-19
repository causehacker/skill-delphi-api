#!/usr/bin/env python3
import argparse
import json
import subprocess
import shlex
from typing import Dict, Any, List

BASE = "https://api.delphi.ai/v3"


def run(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return (p.stdout or "") + ("" if p.returncode == 0 else ("\n" + (p.stderr or "")))


def call_create(api_key: str, slug: str):
    payload = json.dumps({"slug": slug})
    cmd = (
        f"curl -sS -w '\\nHTTP_STATUS:%{{http_code}}' -X POST '{BASE}/conversation' "
        f"-H 'x-api-key: {api_key}' -H 'Content-Type: application/json' -d {shlex.quote(payload)}"
    )
    raw = run(cmd)
    if "HTTP_STATUS:" not in raw:
        return "000", raw.strip(), ""
    body, status = raw.rsplit("HTTP_STATUS:", 1)
    body, status = body.strip(), status.strip()
    cid = ""
    if status == "200":
        try:
            cid = json.loads(body).get("conversation_id", "")
        except Exception:
            pass
    return status, body, cid


def call_stream(api_key: str, slug: str, cid: str, message: str):
    payload = json.dumps({"message": message, "slug": slug, "conversation_id": cid})
    cmd = (
        f"curl -sS -N --max-time 25 -w '\\nHTTP_STATUS:%{{http_code}}' -X POST '{BASE}/stream' "
        f"-H 'x-api-key: {api_key}' -H 'Content-Type: application/json' -d {shlex.quote(payload)}"
    )
    raw = run(cmd)
    if "HTTP_STATUS:" not in raw:
        return "000", raw.strip(), False
    body, status = raw.rsplit("HTTP_STATUS:", 1)
    body, status = body.strip(), status.strip()
    ok = status == "200" and "data:" in body and "[DONE]" in body
    return status, body, ok


def test_one(account: str, api_key: str, slug: str, message: str) -> Dict[str, Any]:
    c_status, c_body, cid = call_create(api_key, slug)
    if c_status != "200" or not cid:
        return {
            "account": account,
            "slug": slug,
            "conversation": "FAIL",
            "stream": "FAIL",
            "overall": "FAIL",
            "note": f"conversation http {c_status}",
            "conversation_http": c_status,
            "stream_http": "-",
            "conversation_id": None,
        }

    s_status, s_body, s_ok = call_stream(api_key, slug, cid, message)
    return {
        "account": account,
        "slug": slug,
        "conversation": "PASS",
        "stream": "PASS" if s_ok else "FAIL",
        "overall": "PASS" if s_ok else "FAIL",
        "note": "" if s_ok else (f"stream http {s_status}" if s_status != "200" else "stream format error"),
        "conversation_http": c_status,
        "stream_http": s_status,
        "conversation_id": cid,
        "stream_preview": s_body[:240],
    }


def main():
    ap = argparse.ArgumentParser(description="Delphi V3 conversation + stream tester")
    ap.add_argument("--api-key", help="Single account API key")
    ap.add_argument("--slug", help="Single account slug")
    ap.add_argument("--account", default="Account", help="Single account label")
    ap.add_argument("--message", default="Please answer in one short sentence to test stream.")
    ap.add_argument(
        "--matrix-json",
        help='JSON array of objects: [{"account":"...","api_key":"...","slug":"..."}]',
    )
    args = ap.parse_args()

    results: List[Dict[str, Any]] = []

    if args.matrix_json:
        items = json.loads(args.matrix_json)
        for i in items:
            results.append(test_one(i.get("account", "Account"), i["api_key"], i["slug"], args.message))
        print(json.dumps(results, indent=2))
        return

    if not args.api_key or not args.slug:
        raise SystemExit("Provide --api-key and --slug, or use --matrix-json")

    print(json.dumps(test_one(args.account, args.api_key, args.slug, args.message), indent=2))


if __name__ == "__main__":
    main()
