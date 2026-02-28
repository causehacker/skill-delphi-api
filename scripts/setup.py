#!/usr/bin/env python3
"""Interactive wizard to create smoke-config.json."""
import json
import os
import sys

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "smoke-config.json")
CONFIG_PATH = os.path.normpath(CONFIG_PATH)

BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ask(prompt: str, default: str = "", required: bool = False, secret: bool = False) -> str:
    """Prompt the user for input with an optional default."""
    suffix = ""
    if default:
        show = "***" if secret else default
        suffix = f" {DIM}[{show}]{RESET}"
    elif required:
        suffix = f" {RED}(required){RESET}"

    while True:
        answer = input(f"  {BLUE}>{RESET} {prompt}{suffix}: ").strip()
        if not answer and default:
            return default
        if not answer and required:
            print(f"    {RED}This field is required.{RESET}")
            continue
        return answer


def ask_bool(prompt: str, default: bool = False) -> bool:
    """Prompt for a yes/no answer."""
    hint = "Y/n" if default else "y/N"
    answer = input(f"  {BLUE}>{RESET} {prompt} {DIM}[{hint}]{RESET}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes", "1", "true")


def ask_choice(prompt: str, choices: list[str], default: str = "") -> str:
    """Prompt for a selection from a list of choices."""
    for i, c in enumerate(choices, 1):
        marker = f" {GREEN}<- default{RESET}" if c == default else ""
        print(f"    {DIM}{i}){RESET} {c}{marker}")
    while True:
        answer = input(f"  {BLUE}>{RESET} {prompt} {DIM}[1-{len(choices)}]{RESET}: ").strip()
        if not answer and default:
            return default
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        if answer in choices:
            return answer
        print(f"    {RED}Pick 1-{len(choices)} or type the value.{RESET}")


def redact(key: str) -> str:
    """Redact an API key for display."""
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]


def main():
    print()
    print(f"  {BOLD}Delphi Smoke Config Setup{RESET}")
    print(f"  {DIM}Creates smoke-config.json for local testing.{RESET}")
    print(f"  {DIM}This file is git-ignored and stays on your machine.{RESET}")
    print()

    # Check for existing config
    existing = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                existing = json.load(f)
            print(f"  {YELLOW}Found existing smoke-config.json{RESET}")
            if ask_bool("Update existing config?", default=True):
                print()
            else:
                print(f"  {DIM}Keeping existing config. Done.{RESET}")
                return
        except (json.JSONDecodeError, OSError):
            print(f"  {YELLOW}Existing config is invalid, starting fresh.{RESET}")
            existing = {}
            print()

    # --- Required ---
    print(f"  {BOLD}Required{RESET}")
    print()

    prev_key = existing.get("api_key", "")
    if prev_key and prev_key != "REPLACE_WITH_DELPHI_API_KEY":
        api_key = ask("API key", default=prev_key, secret=True)
    else:
        api_key = ask("API key", required=True)

    prev_slug = existing.get("slug", "")
    if prev_slug and prev_slug != "REPLACE_WITH_CLONE_SLUG":
        slug = ask("Clone slug", default=prev_slug)
    else:
        slug = ask("Clone slug", required=True)

    print()
    print(f"  {BOLD}Options{RESET}")
    print()

    account = ask("Account display name", default=existing.get("account", "My Delphi Account"))
    message = ask("Test message", default=existing.get("message", "Please answer in one short sentence to test stream."))

    mode = ask_choice(
        "Test mode",
        ["chat", "full"],
        default=existing.get("mode", "chat"),
    )

    # --- Full-mode extras ---
    user_email = ""
    allow_write = False
    tag_name = ""
    info_text = ""

    if mode == "full":
        print()
        print(f"  {BOLD}Full-mode settings{RESET}")
        print()
        user_email = ask("User email for lookup", default=existing.get("user_email", ""))
        allow_write = ask_bool(
            "Enable write endpoints? (creates/deletes test data)",
            default=existing.get("allow_write", False),
        )
        if allow_write:
            print()
            print(f"  {BOLD}Write-mode settings{RESET}")
            print()
            tag_name = ask("Tag name for write tests", default=existing.get("tag_name", "api-test-tag"), required=True)
            info_text = ask("Info text for write tests", default=existing.get("info_text", "safe test note"), required=True)

    # --- Build config ---
    config = {
        "account": account,
        "api_key": api_key,
        "slug": slug,
        "mode": mode,
        "message": message,
        "user_email": user_email,
        "allow_write": allow_write,
        "tag_name": tag_name,
        "info_text": info_text,
    }

    # --- Preview ---
    print()
    print(f"  {BOLD}Preview{RESET}")
    print()
    preview = dict(config)
    preview["api_key"] = redact(api_key)
    print(f"  {json.dumps(preview, indent=2)}")
    print()

    if not ask_bool("Save to smoke-config.json?", default=True):
        print(f"  {DIM}Cancelled. Nothing written.{RESET}")
        return

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    print()
    print(f"  {GREEN}Saved: {CONFIG_PATH}{RESET}")
    print()
    print(f"  {DIM}Run your tests with:{RESET}")
    if mode == "chat":
        print(f"    make smoke")
    else:
        print(f"    make smoke-full")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n  {DIM}Cancelled.{RESET}")
        sys.exit(1)
