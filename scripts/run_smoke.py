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
    args = ap.parse_args()

    if not os.path.exists(args.config):
        die(f"Config file not found: {args.config}. Copy smoke-config.example.json to smoke-config.json and fill it in.")

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    api_key = cfg.get("api_key", "").strip()
    slug = cfg.get("slug", "").strip()
    account = cfg.get("account", "Account")
    message = cfg.get("message", "Please answer in one short sentence to test stream.")

    if not api_key or api_key == "REPLACE_WITH_DELPHI_API_KEY":
        die("Please set api_key in smoke-config.json")
    if not slug or slug == "REPLACE_WITH_CLONE_SLUG":
        die("Please set slug in smoke-config.json")

    cmd = [
        "python3",
        "delphi-api-safe/scripts/test_delphi_v3.py",
        "--api-key",
        api_key,
        "--slug",
        slug,
        "--account",
        account,
        "--message",
        message,
        "--mode",
        args.mode,
    ]

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

    display_cmd = " ".join(shlex.quote(x) for x in cmd)
    if api_key:
        display_cmd = display_cmd.replace(api_key, "***redacted***")

    print("Running:")
    print(display_cmd)

    p = subprocess.run(cmd, text=True)
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
