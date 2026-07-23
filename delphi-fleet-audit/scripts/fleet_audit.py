#!/usr/bin/env python3
"""Fleet-wide Delphi health check: every account in keys.json, one matrix.

Per account: clone discovery (GET /v3/clone), conversation create, stream check.
With --sizing, adds audience numbers (total / real / filtered-out) via the
paginated /v3/users sweep and the same is_real() rule as audience_audit.py.

READ-ONLY apart from throwaway conversations. Paced between accounts and pages.
Keys are always redacted to dsk-****<last4> in output.

Usage:
    python3 scripts/fleet_audit.py                       # all accounts in keys.json
    python3 scripts/fleet_audit.py --sizing              # + audience sizing
    python3 scripts/fleet_audit.py --accounts a,b        # subset
    python3 scripts/fleet_audit.py --keys "dsk-x,dsk-y"  # explicit keys, no keys.json
    python3 scripts/fleet_audit.py --json --out out/fleet.json
"""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.delphi.ai"
UA = "delphi-fleet-audit/1.0"  # default python-urllib UA is 403'd by Cloudflare

# Same rule as audience_audit.py — keep in sync if that list changes.
FAKE_MARKERS = ("example", "fake", "test", "noinput", "smoke",
                "placeholder", "dummy", "invalid", "@test.", "no-reply", "noreply")


def is_real(email: str) -> bool:
    if not email or "@" not in email:
        return False
    local, _, domain = email.lower().partition("@")
    if "." not in domain or not local:
        return False
    return not any(m in email.lower() for m in FAKE_MARKERS)


def redact(key: str) -> str:
    return f"dsk-****{key[-4:]}" if len(key) > 8 else "dsk-****"


def call(method: str, path: str, key: str, payload=None, retries: int = 3, timeout: int = 45):
    """Returns (status, parsed-json-or-text). Retries 429/5xx with backoff."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method=method,
        headers={"x-api-key": key, "Content-Type": "application/json", "User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                try:
                    return r.status, json.loads(body)
                except Exception:
                    return r.status, body.decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return e.code, e.read().decode("utf-8", "replace")[:400]
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return 0, str(e)


def load_accounts(args) -> dict:
    if args.keys:
        return {f"key{i+1}": k.strip() for i, k in enumerate(args.keys.split(",")) if k.strip()}
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "keys.json")
    if not os.path.exists(path):
        sys.exit("No keys.json at repo root and no --keys given. Create keys.json "
                 '(gitignored): { "accounts": { "<name>": "dsk-..." } }')
    accounts = json.load(open(path)).get("accounts", {})
    if args.accounts:
        wanted = [a.strip() for a in args.accounts.split(",")]
        missing = [a for a in wanted if a not in accounts]
        if missing:
            sys.exit(f"Not in keys.json: {', '.join(missing)}. "
                     f"Available: {', '.join(sorted(accounts))}")
        accounts = {a: accounts[a] for a in wanted}
    if not accounts:
        sys.exit("keys.json has no accounts.")
    return accounts


def health_check(key: str, message: str) -> dict:
    """clone -> conversation -> stream, house PASS/FAIL semantics."""
    out = {"clone_name": None, "note": ""}

    st, body = call("GET", "/v3/clone", key)
    out["clone_http"] = st
    if st == 200 and isinstance(body, dict):
        clone = body.get("clone", body)
        out["clone_name"] = clone.get("name")
        out["clone"] = "PASS"
    else:
        out["clone"] = "FAIL"
        out["conversation"] = out["stream"] = "-"
        out["overall"] = "FAIL"
        out["note"] = "key not active/authorized" if st == 403 else f"clone http {st}"
        return out

    st, body = call("POST", "/v3/conversation", key, {})
    out["conversation_http"] = st
    cid = body.get("conversation_id") if st == 200 and isinstance(body, dict) else None
    if not cid:
        out["conversation"] = "FAIL"
        out["stream"] = "-"
        out["overall"] = "FAIL"
        out["note"] = f"conversation http {st}"
        return out
    out["conversation"] = "PASS"

    st, body = call("POST", "/v3/stream", key, {"message": message, "conversation_id": cid},
                    retries=1, timeout=30)
    out["stream_http"] = st
    text = body if isinstance(body, str) else json.dumps(body)
    s_ok = st == 200 and "data:" in text and "[DONE]" in text
    out["stream"] = "PASS" if s_ok else "FAIL"
    out["overall"] = "PASS" if s_ok else "FAIL"
    if not s_ok:
        out["note"] = f"stream http {st}" if st != 200 else "stream format error"
    return out


def audience_sizing(key: str) -> dict:
    users, cursor = [], None
    while True:
        url = "/v3/users?limit=1000" + (
            f"&cursor={urllib.parse.quote(cursor, safe='')}" if cursor else "")
        st, d = call("GET", url, key)
        if st != 200 or not isinstance(d, dict):
            return {"sizing_error": f"users http {st}"}
        users.extend(d.get("users", []))
        cursor = d.get("next_cursor")
        if not d.get("has_more") or not cursor:
            break
        time.sleep(0.5)
    real = sum(1 for u in users if is_real(u.get("email", "")))
    return {"total_users": len(users), "real_users": real,
            "filtered_out": len(users) - real}


def main() -> int:
    ap = argparse.ArgumentParser(description="Fleet-wide Delphi health check across keys.json accounts.")
    ap.add_argument("--accounts", help="Comma-separated subset of keys.json account names.")
    ap.add_argument("--keys", help="Comma-separated explicit API keys (skips keys.json).")
    ap.add_argument("--sizing", action="store_true", help="Add audience sizing (total/real/filtered).")
    ap.add_argument("--message", default="Please answer in one short sentence to test stream.")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of the text matrix.")
    ap.add_argument("--out", help="Also write full JSON to this path (use out/ — gitignored).")
    args = ap.parse_args()

    accounts = load_accounts(args)
    results = []
    for i, (name, key) in enumerate(accounts.items()):
        print(f"[{i+1}/{len(accounts)}] {name}...", file=sys.stderr)
        row = {"account": name, "key": redact(key)}
        row.update(health_check(key, args.message))
        if args.sizing and row["overall"] != "FAIL":
            row.update(audience_sizing(key))
        results.append(row)
        if i < len(accounts) - 1:
            time.sleep(1.0)  # pace between accounts

    report = {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "accounts_checked": len(results),
              "passed": sum(1 for r in results if r.get("overall") == "PASS"),
              "results": results}

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"snapshot -> {args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        cols = ["account", "key", "clone_name", "conversation", "stream", "overall", "note"]
        if args.sizing:
            cols[6:6] = ["total_users", "real_users", "filtered_out"]
        widths = {c: max(len(c), *(len(str(r.get(c, "") or "")) for r in results)) for c in cols}
        line = "  ".join(c.upper().ljust(widths[c]) for c in cols)
        print("\n" + line)
        print("-" * len(line))
        for r in results:
            print("  ".join(str(r.get(c, "") or "").ljust(widths[c]) for c in cols))
        print(f"\n{report['passed']}/{report['accounts_checked']} accounts PASS")

    return 0 if report["passed"] == report["accounts_checked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
