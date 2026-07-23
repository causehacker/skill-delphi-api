#!/usr/bin/env python3
"""Coverage parity check: is every V3 endpoint present on every surface?

Parses four surfaces and prints a METHOD /v3/path x surface matrix:

  references : delphi-api-safe/references/v3-endpoints.md
  skill      : delphi-api-safe/SKILL.md
  tests      : delphi-api-safe/scripts/test_delphi_v3.py
  playground : docs/api-reference.html (ENDPOINTS array)

Path parameters are normalized ({user_id}, {id}, <cid>, f-string vars -> {}),
query strings stripped, so the same endpoint matches across surfaces.

Exit code 0 = full parity, 1 = gaps found (usable in CI or pre-commit).

Usage:
    python3 delphi-docs-sync/scripts/coverage_check.py
    python3 delphi-docs-sync/scripts/coverage_check.py --json
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SURFACES = {
    "references": "delphi-api-safe/references/v3-endpoints.md",
    "skill": "delphi-api-safe/SKILL.md",
    "tests": "delphi-api-safe/scripts/test_delphi_v3.py",
    "playground": "docs/api-reference.html",
}

METHODS = "GET|POST|PUT|PATCH|DELETE"

# Surfaces where an endpoint may be legitimately absent, with the reason.
# Keep this list short and honest — every entry is a conscious exception.
KNOWN_EXCEPTIONS = {
    # ("METHOD /v3/path", "surface"): "reason"
}


def norm(method: str, path: str) -> str:
    """Normalize 'METHOD /v3/path' so the same endpoint matches across surfaces."""
    path = path.split("?")[0].rstrip("/")
    path = re.sub(r"\{[^}]*\}", "{}", path)   # {user_id}, f-string {cid} -> {}
    path = re.sub(r"<[^>]*>", "{}", path)     # <cid> -> {}
    if not path.startswith("/v3"):
        path = "/v3" + path
    return f"{method.upper()} {path}"


def read(relpath: str) -> str:
    p = os.path.join(ROOT, relpath)
    if not os.path.exists(p):
        return ""
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def parse_markdown(text: str) -> set:
    """Backtick-quoted endpoints in .md files: `POST /v3/search/query`.
    Also handles combined forms like `POST/DELETE /v3/...` and
    `GET /v3/conversation/list?email=...`."""
    out = set()
    for m in re.finditer(rf"`((?:{METHODS})(?:/(?:{METHODS}))*)\s+(/v3/[^`\s]+)`", text):
        for method in m.group(1).split("/"):
            out.add(norm(method, m.group(2)))
    return out


def parse_tests(text: str) -> set:
    """http_json("METHOD", "/path") / http_binary(...) calls in test_delphi_v3.py.
    Paths there omit the /v3 prefix (BASE includes it) and may be f-strings."""
    out = set()
    for m in re.finditer(
        rf"http_(?:json|binary)\(\s*\n?\s*\"({METHODS})\",\s*\n?\s*f?\"([^\"]+)\"", text
    ):
        out.add(norm(m.group(1), m.group(2)))
    return out


def tests_path_literals(text: str) -> set:
    """Fallback for loop-driven calls (e.g. `for label, path in [("tier",
    f"/users/{uid}/tier"), ...]` passed to http_json("GET", path)): every
    string literal in the tests file that looks like an endpoint path,
    normalized without a method."""
    out = set()
    for m in re.finditer(r"f?\"(/(?:users|conversation|tags|clone|stream|voice|questions|search)[^\"]*)\"", text):
        out.add(norm("GET", m.group(1)).split(" ", 1)[1])
    return out


def parse_playground(text: str) -> set:
    """ENDPOINTS array cards: method: "POST", path: "/v3/..." """
    out = set()
    for m in re.finditer(rf"method:\s*\"({METHODS})\",\s*path:\s*\"([^\"]+)\"", text):
        out.add(norm(m.group(1), m.group(2)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Endpoint coverage parity check across repo surfaces.")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of a table.")
    args = ap.parse_args()

    parsers = {
        "references": parse_markdown,
        "skill": parse_markdown,
        "tests": parse_tests,
        "playground": parse_playground,
    }
    coverage = {s: parsers[s](read(path)) for s, path in SURFACES.items()}
    test_paths = tests_path_literals(read(SURFACES["tests"]))
    all_eps = sorted(set().union(*coverage.values()))

    gaps = []
    rows = []
    for ep in all_eps:
        row = {"endpoint": ep}
        for s in SURFACES:
            present = ep in coverage[s]
            if not present and s == "tests":
                # loop-driven calls pass the path as a variable; match path-only
                present = ep.split(" ", 1)[1] in test_paths
            row[s] = present
            if not present and (ep, s) not in KNOWN_EXCEPTIONS:
                gaps.append({"endpoint": ep, "missing_from": s})
        rows.append(row)

    if args.json:
        print(json.dumps({"endpoints": rows, "gaps": gaps,
                          "surface_counts": {s: len(v) for s, v in coverage.items()}}, indent=2))
        return 1 if gaps else 0

    w = max(len(e) for e in all_eps) if all_eps else 20
    header = f"{'ENDPOINT'.ljust(w)}  " + "  ".join(s.ljust(10) for s in SURFACES)
    print(header)
    print("-" * len(header))
    for row in rows:
        marks = "  ".join(("yes" if row[s] else "MISSING").ljust(10) for s in SURFACES)
        print(f"{row['endpoint'].ljust(w)}  {marks}")
    print("-" * len(header))
    print(f"{len(all_eps)} endpoints | " + " | ".join(f"{s}: {len(coverage[s])}" for s in SURFACES))
    if gaps:
        print(f"\n{len(gaps)} GAP(S):")
        for g in gaps:
            print(f"  {g['endpoint']} missing from {g['missing_from']}")
        return 1
    print("\nFull parity across all surfaces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
