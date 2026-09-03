#!/usr/bin/env python3
"""Verify that the interactive playground covers every live Delphi operation.

The checker fetches both authenticated OpenAPI documents in memory and compares
their method/path pairs with the cards in ``docs/api-reference.html``. It never
prints or persists the API key.

Usage:
    DELPHI_API_KEY="..." python3 scripts/check_openapi_coverage.py
    python3 scripts/check_openapi_coverage.py --config smoke-config.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Final

API_BASE: Final = "https://api.delphi.ai"
HTTP_METHODS: Final = frozenset({"get", "post", "put", "patch", "delete"})
ENDPOINT_PATTERN: Final = re.compile(
    r'\{\s*method:\s*"([A-Z]+)",\s*path:\s*"([^"]+)"'
)


def resolve_api_key(config_path: Path) -> str:
    """Resolve the API key from the environment or a local ignored config."""
    environment_key = os.environ.get("DELPHI_API_KEY", "").strip()
    if environment_key:
        return environment_key

    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config_key = str(config.get("api_key", "")).strip()
        if config_key and config_key != "REPLACE_WITH_DELPHI_API_KEY":
            return config_key

    raise SystemExit(
        "Set DELPHI_API_KEY or provide --config pointing to a local config."
    )


def fetch_openapi(version: str, api_key: str) -> dict:
    """Fetch and minimally validate one live OpenAPI document."""
    request = urllib.request.Request(
        f"{API_BASE}/{version}/openapi.json",
        headers={
            "x-api-key": api_key,
            "User-Agent": "delphi-api-safe-contract-check/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        document = json.load(response)

    if document.get("openapi") != "3.1.0" or not document.get("paths"):
        raise RuntimeError(f"{version}: response is not the expected OpenAPI document")
    return document


def get_live_operations(document: dict, version: str) -> set[tuple[str, str]]:
    """Return version-prefixed method/path pairs from an OpenAPI document."""
    return {
        (method.upper(), f"/{version}{path}")
        for path, path_item in document["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }


def get_playground_operations(html: str, version: str) -> set[tuple[str, str]]:
    """Return method/path pairs from one playground endpoint array."""
    marker = f"const ENDPOINTS_{version.upper()} = ["
    start = html.index(marker)
    end = html.index("\n];", start)
    return set(ENDPOINT_PATTERN.findall(html[start:end]))


def main() -> int:
    """Fetch both contracts and fail if playground coverage has drifted."""
    parser = argparse.ArgumentParser(
        description="Compare live Delphi OpenAPI operations with playground cards."
    )
    parser.add_argument("--config", type=Path, default=Path("smoke-config.json"))
    parser.add_argument(
        "--playground", type=Path, default=Path("docs/api-reference.html")
    )
    args = parser.parse_args()

    api_key = resolve_api_key(args.config)
    html = args.playground.read_text(encoding="utf-8")
    failed = False

    for version in ("v3", "v4"):
        document = fetch_openapi(version, api_key)
        live = get_live_operations(document, version)
        playground = get_playground_operations(html, version)
        missing = sorted(live - playground)
        extra = sorted(playground - live)
        print(
            f"{version}: {len(document['paths'])} paths, {len(live)} operations, "
            f"{len(playground)} playground cards"
        )
        for method, path in missing:
            print(f"  MISSING {method} {path}")
        for method, path in extra:
            print(f"  EXTRA   {method} {path}")
        failed = failed or bool(missing or extra)

    if failed:
        print("FAIL: playground and live contracts differ.", file=sys.stderr)
        return 1

    print("PASS: playground covers every live V3 and V4 operation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
