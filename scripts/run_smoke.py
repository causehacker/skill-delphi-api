#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import subprocess
import sys


def die(msg: str):
    print(f"ERROR: {msg}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Run Delphi smoke tests from a simple JSON config")
    ap.add_argument("--config", default="smoke-config.json")
    ap.add_argument("--mode", choices=["chat", "full"], default="chat")
    ap.add_argument("--search", action="store_true", help="Force search tests on (overrides config)")
    ap.add_argument("--api", choices=["v3", "v4"], default="v3",
                    help="Which API surface to smoke. v4 is the Developer Platform "
                         "(contacts/content/webhooks) and is read-only by default.")
    args = ap.parse_args()

    if not os.path.exists(args.config):
        die(f"Config file not found: {args.config}. Copy smoke-config.example.json to smoke-config.json and fill it in.")

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    api_key = cfg.get("api_key", "").strip()
    account = cfg.get("account", "Account")
    message = cfg.get("message", "Please answer in one short sentence to test stream.")

    if not api_key or api_key == "REPLACE_WITH_DELPHI_API_KEY":
        die("Please set api_key in smoke-config.json")

    if args.api == "v4":
        # V4 harness is read-only unless the config explicitly opts into the two
        # metered endpoints. Destructive V4 endpoints are not exposed at all.
        cmd = [
            "python3",
            "delphi-api-safe/scripts/test_delphi_v4.py",
            "--api-key",
            api_key,
        ]
        if cfg.get("v4_test_generate", False):
            cmd.append("--test-generate")
            idem = str(cfg.get("v4_idempotency_key", "")).strip()
            if idem:
                cmd += ["--idempotency-key", idem]
        if cfg.get("v4_test_llm", False):
            cmd.append("--test-llm")
        run_cmd(cmd, api_key)
        return

    cmd = [
        "python3",
        "delphi-api-safe/scripts/test_delphi_v3.py",
        "--api-key",
        api_key,
        "--account",
        account,
        "--message",
        message,
        "--mode",
        args.mode,
    ]

    # Search tests (Immortal plan feature)
    if args.search or cfg.get("test_search", False):
        search_query = cfg.get("search_query", "What is your background?").strip()
        cmd += ["--test-search", "--search-query", search_query]

    if args.mode == "full":
        user_email = cfg.get("user_email", "").strip()
        if user_email:
            cmd += ["--user-email", user_email]

        if cfg.get("allow_write", False):
            tag_name = cfg.get("tag_name", "").strip()
            info_text = cfg.get("info_text", "").strip()
            if not tag_name:
                die("allow_write=true requires tag_name in smoke-config.json")
            if not info_text:
                die("allow_write=true requires info_text in smoke-config.json")
            cmd += ["--allow-write", "--tag-name", tag_name, "--info-text", info_text]

    run_cmd(cmd, api_key)


def run_cmd(cmd, api_key):
    display_cmd = " ".join(shlex.quote(x) for x in cmd)
    if api_key:
        display_cmd = display_cmd.replace(api_key, "***redacted***")

    # flush=True so the preamble lands before the subprocess's own output when
    # stdout is a pipe (otherwise Python's block buffering prints it last).
    print("Running:", flush=True)
    print(display_cmd, flush=True)

    p = subprocess.run(cmd, text=True)
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
