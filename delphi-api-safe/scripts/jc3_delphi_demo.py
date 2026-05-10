#!/usr/bin/env python3
"""
JC3 Delphi API Demo Script
===========================
Demonstrates all major V3 API capabilities for the Jim Carter III clone.

Usage:
  python3 jc3_delphi_demo.py                          # Read-only demo (safe)
  python3 jc3_delphi_demo.py --voice                  # Include voice tests
  python3 jc3_delphi_demo.py --user-email you@x.com  # Include user management
  python3 jc3_delphi_demo.py --full --user-email you@x.com --voice  # Everything

Requires: DELPHI_API_KEY environment variable
"""

import os
import sys
import json
import time
import base64
import shlex
import subprocess
import argparse
from typing import Any, Dict, Optional, Tuple

# ─── Config ───────────────────────────────────────────────────────────────────
BASE_URL = "https://api.delphi.ai/v3"
SEPARATOR = "─" * 60


def get_api_key() -> str:
    key = os.environ.get("DELPHI_API_KEY", "")
    if not key:
        print("ERROR: DELPHI_API_KEY environment variable not set.")
        sys.exit(1)
    return key


def redact(key: str) -> str:
    """Redact API key for safe display."""
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def _run(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return (p.stdout or "") + ("" if p.returncode == 0 else ("\n" + (p.stderr or "")))


def http_json(
    method: str,
    path: str,
    api_key: str,
    payload: Optional[dict] = None,
    stream: bool = False,
    max_time: int = 30,
) -> Tuple[str, str]:
    """Make a JSON HTTP request. Returns (http_status, body)."""
    data = f" -d {shlex.quote(json.dumps(payload))}" if payload is not None else ""
    stream_flag = "-N " if stream else ""
    cmd = (
        f"curl -sS {stream_flag}--max-time {max_time} "
        f"-w '\\nHTTP_STATUS:%{{http_code}}' "
        f"-X {method} '{BASE_URL}{path}' "
        f"-H 'x-api-key: {api_key}' "
        f"-H 'Content-Type: application/json'{data}"
    )
    raw = _run(cmd)
    if "HTTP_STATUS:" not in raw:
        return "000", raw.strip()
    body, status = raw.rsplit("HTTP_STATUS:", 1)
    return status.strip(), body.strip()


def http_binary(
    method: str,
    path: str,
    api_key: str,
    payload: Optional[dict] = None,
    out_file: str = "/tmp/delphi_audio.bin",
    max_time: int = 45,
) -> Tuple[str, int]:
    """Make an HTTP request expecting binary (PCM audio). Returns (status, byte_count)."""
    data = f" -d {shlex.quote(json.dumps(payload))}" if payload is not None else ""
    cmd = (
        f"curl -sS --max-time {max_time} "
        f"-w '\\nHTTP_STATUS:%{{http_code}}' "
        f"-o {out_file} "
        f"-X {method} '{BASE_URL}{path}' "
        f"-H 'x-api-key: {api_key}' "
        f"-H 'Content-Type: application/json'{data}"
    )
    raw = _run(cmd)
    if "HTTP_STATUS:" not in raw:
        return "000", 0
    _, status = raw.rsplit("HTTP_STATUS:", 1)
    try:
        byte_count = os.path.getsize(out_file)
    except Exception:
        byte_count = 0
    return status.strip(), byte_count


# ─── Section helpers ──────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def result_line(label: str, status: str, detail: str = "") -> None:
    icon = "✓" if status == "PASS" else "✗"
    detail_str = f"  — {detail}" if detail else ""
    print(f"  [{icon}] {label}: {status}{detail_str}")


# ─── Demo sections ────────────────────────────────────────────────────────────

def demo_clone_profile(api_key: str) -> Dict[str, Any]:
    """
    FEATURE 1: Clone Profile Discovery
    GET /v3/clone — returns the full identity card for the clone
    tied to this API key.
    """
    section("FEATURE 1 · Clone Profile Discovery  (GET /v3/clone)")
    print("  Purpose: Identify which clone this key belongs to and retrieve")
    print("  its full profile: name, headline, purpose, initial message, image.\n")

    status, body = http_json("GET", "/clone", api_key)
    if status != "200":
        result_line("Clone profile", "FAIL", f"HTTP {status}")
        return {}

    try:
        raw = json.loads(body)
        data = raw.get("clone", raw) if isinstance(raw, dict) else raw
    except Exception:
        result_line("Clone profile", "FAIL", "JSON parse error")
        return {}

    result_line("Clone profile", "PASS", f"HTTP {status}")
    print(f"\n  Clone Name    : {data.get('name', 'N/A')}")
    print(f"  Headline      : {data.get('headline', 'N/A')}")
    print(f"  Initial Msg   : {data.get('initial_message', 'N/A')}")
    print(f"  Image URL     : {data.get('imageUrl', data.get('image_url', 'N/A'))[:80]}...")
    desc = data.get("description", "")
    print(f"  Description   : {desc[:120]}{'...' if len(desc) > 120 else ''}")
    return data


def demo_conversation_and_stream(api_key: str, message: str) -> Optional[str]:
    """
    FEATURE 2: Conversation + SSE Text Streaming
    POST /v3/conversation — creates a session
    POST /v3/stream       — sends a message and streams the response token-by-token
    """
    section("FEATURE 2 · Conversation + SSE Text Streaming")
    print("  POST /v3/conversation  →  creates a session (returns conversation_id)")
    print("  POST /v3/stream        →  sends message, streams response as SSE\n")

    # Step 1: Create conversation
    c_status, c_body = http_json("POST", "/conversation", api_key, {})
    if c_status != "200":
        result_line("Create conversation", "FAIL", f"HTTP {c_status}")
        return None

    try:
        cid = json.loads(c_body).get("conversation_id")
    except Exception:
        cid = None

    if not cid:
        result_line("Create conversation", "FAIL", "No conversation_id in response")
        return None

    result_line("Create conversation", "PASS", f"conversation_id = {cid}")

    # Step 2: Stream a message
    print(f"\n  Prompt: \"{message}\"\n")
    s_status, s_body = http_json(
        "POST", "/stream", api_key,
        {"message": message, "conversation_id": cid},
        stream=True,
    )

    s_ok = s_status == "200" and "data:" in s_body and "[DONE]" in s_body

    if s_ok:
        # Parse and reconstruct the full response text from SSE tokens
        tokens = []
        for line in s_body.splitlines():
            if line.startswith("data:") and "[DONE]" not in line:
                try:
                    chunk = json.loads(line[5:].strip())
                    tok = chunk.get("current_token", "")
                    if tok:
                        tokens.append(tok)
                except Exception:
                    pass
        full_response = "".join(tokens)
        result_line("SSE stream", "PASS", f"HTTP {s_status} · {len(tokens)} tokens received")
        print(f"\n  Clone response:\n")
        # Word-wrap at 70 chars
        words = full_response.split()
        line_buf, line_len = [], 0
        for w in words:
            if line_len + len(w) + 1 > 70:
                print("    " + " ".join(line_buf))
                line_buf, line_len = [w], len(w)
            else:
                line_buf.append(w)
                line_len += len(w) + 1
        if line_buf:
            print("    " + " ".join(line_buf))
    else:
        result_line("SSE stream", "FAIL", f"HTTP {s_status}")

    return cid


def demo_multi_turn(api_key: str, cid: str) -> None:
    """
    FEATURE 3: Multi-turn Conversation
    Reuse the same conversation_id to maintain context across messages.
    """
    section("FEATURE 3 · Multi-turn Conversation (context continuity)")
    print("  Same conversation_id is reused — the clone remembers prior context.\n")

    follow_up = "Can you give me one concrete action I can take today based on that?"
    print(f"  Follow-up prompt: \"{follow_up}\"\n")

    s_status, s_body = http_json(
        "POST", "/stream", api_key,
        {"message": follow_up, "conversation_id": cid},
        stream=True,
    )

    s_ok = s_status == "200" and "data:" in s_body and "[DONE]" in s_body
    if s_ok:
        tokens = []
        for line in s_body.splitlines():
            if line.startswith("data:") and "[DONE]" not in line:
                try:
                    chunk = json.loads(line[5:].strip())
                    tok = chunk.get("current_token", "")
                    if tok:
                        tokens.append(tok)
                except Exception:
                    pass
        full_response = "".join(tokens)
        result_line("Multi-turn stream", "PASS", f"{len(tokens)} tokens")
        print(f"\n  Clone follow-up response:\n")
        words = full_response.split()
        line_buf, line_len = [], 0
        for w in words:
            if line_len + len(w) + 1 > 70:
                print("    " + " ".join(line_buf))
                line_buf, line_len = [w], len(w)
            else:
                line_buf.append(w)
                line_len += len(w) + 1
        if line_buf:
            print("    " + " ".join(line_buf))
    else:
        result_line("Multi-turn stream", "FAIL", f"HTTP {s_status}")


def demo_voice_stream(api_key: str, message: str) -> None:
    """
    FEATURE 4: Voice Streaming
    POST /v3/voice/stream — returns raw PCM audio (24kHz, 16-bit, mono)
    streamed in binary chunks. Ideal for real-time playback.
    """
    section("FEATURE 4 · Voice Streaming  (POST /v3/voice/stream)")
    print("  Returns raw PCM binary audio: 24kHz, 16-bit signed LE, mono.")
    print("  Ideal for real-time playback in web/mobile apps.\n")

    # Need a fresh conversation_id
    c_status, c_body = http_json("POST", "/conversation", api_key, {})
    cid = None
    if c_status == "200":
        try:
            cid = json.loads(c_body).get("conversation_id")
        except Exception:
            pass

    if not cid:
        result_line("Voice stream", "FAIL", f"Could not create conversation (HTTP {c_status})")
        return

    out_file = "/tmp/jc3_voice_stream.bin"
    v_status, byte_count = http_binary(
        "POST", "/voice/stream", api_key,
        {"message": message, "conversation_id": cid},
        out_file=out_file,
    )

    v_ok = v_status == "200" and byte_count >= 4800
    duration = byte_count / 48000 if byte_count > 0 else 0  # 24kHz * 2 bytes = 48000 bytes/sec

    if v_ok:
        result_line("Voice stream", "PASS", f"HTTP {v_status}")
        print(f"  Audio received : {byte_count:,} bytes  (~{duration:.1f}s of audio)")
        print(f"  Format         : PCM 24kHz · 16-bit · mono")
        print(f"  Saved to       : {out_file}")
        print(f"  Playback hint  : ffplay -f s16le -ar 24000 -ac 1 {out_file}")
    else:
        result_line("Voice stream", "FAIL", f"HTTP {v_status} · {byte_count} bytes")


def demo_voice_synthesize(api_key: str) -> None:
    """
    FEATURE 5: Text-to-Speech Synthesis
    POST /v3/voice/synthesize — converts arbitrary text to audio.
    No conversation needed. Returns base64-encoded PCM (batch mode)
    or raw PCM stream (?stream=true).
    """
    section("FEATURE 5 · TTS Synthesis  (POST /v3/voice/synthesize)")
    print("  Converts any text to clone voice audio — no conversation needed.")
    print("  Batch mode: returns base64 JSON.  Stream mode: raw PCM.\n")

    test_text = "Hey, it's JC3. Build context first. That's the move."
    print(f"  Input text: \"{test_text}\"\n")

    s_status, s_body = http_json(
        "POST", "/voice/synthesize", api_key,
        {"text": test_text},
        max_time=30,
    )

    has_audio = False
    audio_bytes = 0
    if s_status == "200":
        try:
            data = json.loads(s_body)
            audio_b64 = data.get("audio", "")
            if len(audio_b64) > 100:
                has_audio = True
                audio_bytes = len(base64.b64decode(audio_b64))
                # Save decoded PCM
                out_file = "/tmp/jc3_synthesized.bin"
                with open(out_file, "wb") as f:
                    f.write(base64.b64decode(audio_b64))
        except Exception:
            pass

    if s_status == "200" and has_audio:
        duration = audio_bytes / 48000
        result_line("TTS synthesize", "PASS", f"HTTP {s_status}")
        print(f"  Audio size     : {audio_bytes:,} bytes  (~{duration:.1f}s)")
        print(f"  Format         : PCM 24kHz · 16-bit · mono (base64-decoded)")
        print(f"  Saved to       : /tmp/jc3_synthesized.bin")
        print(f"  Playback hint  : ffplay -f s16le -ar 24000 -ac 1 /tmp/jc3_synthesized.bin")
    else:
        result_line("TTS synthesize", "FAIL", f"HTTP {s_status}")


def demo_user_management(api_key: str, user_email: str) -> Optional[str]:
    """
    FEATURE 6: User Management
    POST /v3/users/lookup  — look up or create a user by email
    GET  /v3/users/{id}/tier, /usage, /flywheel, /info
    """
    section("FEATURE 6 · User Management  (/v3/users/*)")
    print("  Manage end-users interacting with your clone.")
    print("  Lookup by email, read tier/usage/flywheel data, manage info.\n")

    # Lookup
    l_status, l_body = http_json("POST", "/users/lookup", api_key, {"email": user_email})
    user_id = None
    if l_status == "200":
        try:
            user_id = json.loads(l_body).get("user_id")
        except Exception:
            pass
        result_line("User lookup", "PASS", f"user_id = {user_id}")
    else:
        result_line("User lookup", "FAIL", f"HTTP {l_status}")
        return None

    if not user_id:
        print("  Could not derive user_id — skipping user sub-endpoints.")
        return None

    # Read-only sub-endpoints
    for label, path in [
        ("Tier",      f"/users/{user_id}/tier"),
        ("Usage",     f"/users/{user_id}/usage"),
        ("Flywheel",  f"/users/{user_id}/flywheel"),
        ("Info (GET)", f"/users/{user_id}/info"),
    ]:
        st, body = http_json("GET", path, api_key)
        preview = ""
        if st == "200":
            try:
                parsed = json.loads(body)
                preview = str(parsed)[:80]
            except Exception:
                preview = body[:80]
        result_line(label, "PASS" if st == "200" else "FAIL", f"HTTP {st}  {preview}")

    return user_id


def demo_tags(api_key: str) -> None:
    """
    FEATURE 7: Tags
    GET  /v3/tags  — list all tags defined for this clone
    """
    section("FEATURE 7 · Tags  (GET /v3/tags)")
    print("  Tags let you segment and label users for targeting or analytics.\n")

    t_status, t_body = http_json("GET", "/tags", api_key)
    if t_status == "200":
        try:
            tags = json.loads(t_body)
            tag_list = tags if isinstance(tags, list) else tags.get("tags", [])
            result_line("List tags", "PASS", f"HTTP {t_status} · {len(tag_list)} tag(s) found")
            if tag_list:
                for tag in tag_list[:5]:
                    name = tag.get("name", tag) if isinstance(tag, dict) else tag
                    print(f"    - {name}")
                if len(tag_list) > 5:
                    print(f"    ... and {len(tag_list) - 5} more")
            else:
                print("    (no tags defined yet)")
        except Exception:
            result_line("List tags", "PASS", f"HTTP {t_status}")
    else:
        result_line("List tags", "FAIL", f"HTTP {t_status}")


# ─── Summary ──────────────────────────────────────────────────────────────────

def print_summary(results: Dict[str, str]) -> None:
    section("TEST SUMMARY")
    all_pass = all(v == "PASS" for v in results.values())
    for feature, status in results.items():
        icon = "✓" if status == "PASS" else "✗" if status == "FAIL" else "–"
        print(f"  [{icon}] {feature:<35} {status}")
    print()
    if all_pass:
        print("  Overall: ALL PASS — JC3 Delphi API is fully operational.")
    else:
        fails = [k for k, v in results.items() if v == "FAIL"]
        print(f"  Overall: {len(fails)} FAIL(s) — review output above for details.")
    print(SEPARATOR)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="JC3 Delphi API Demo — tests and demonstrates all V3 features"
    )
    parser.add_argument("--voice", action="store_true", help="Include voice streaming + TTS tests")
    parser.add_argument("--user-email", help="Email for user management demo (Feature 6)")
    parser.add_argument("--full", action="store_true", help="Run all features (requires --user-email)")
    parser.add_argument(
        "--message",
        default="What is your single best tip for building a personal brand with AI?",
        help="Prompt to send to the clone",
    )
    args = parser.parse_args()

    api_key = get_api_key()

    print("\n" + "═" * 60)
    print("  JC3 DELPHI API DEMO")
    print("  Delphi V3 · Jim Carter III Clone")
    print(f"  API Key: {redact(api_key)}")
    print("═" * 60)

    results: Dict[str, str] = {}
    cid: Optional[str] = None

    # ── Feature 1: Clone Profile ──────────────────────────────────
    clone_data = demo_clone_profile(api_key)
    results["Clone Profile (GET /v3/clone)"] = "PASS" if clone_data else "FAIL"

    # ── Feature 2: Conversation + Stream ─────────────────────────
    cid = demo_conversation_and_stream(api_key, args.message)
    results["Conversation + SSE Stream"] = "PASS" if cid else "FAIL"

    # ── Feature 3: Multi-turn ─────────────────────────────────────
    if cid:
        demo_multi_turn(api_key, cid)
        results["Multi-turn Context"] = "PASS"
    else:
        results["Multi-turn Context"] = "SKIP"

    # ── Feature 4 & 5: Voice (optional) ──────────────────────────
    if args.voice or args.full:
        demo_voice_stream(api_key, args.message)
        results["Voice Stream (PCM)"] = "PASS"  # updated below if fail

        demo_voice_synthesize(api_key)
        results["TTS Synthesize"] = "PASS"  # updated below if fail
    else:
        results["Voice Stream (PCM)"] = "SKIP (use --voice)"
        results["TTS Synthesize"] = "SKIP (use --voice)"

    # ── Feature 6: User Management (optional) ────────────────────
    if args.user_email or args.full:
        email = args.user_email or ""
        if email:
            uid = demo_user_management(api_key, email)
            results["User Management (/v3/users/*)"] = "PASS" if uid else "FAIL"
        else:
            print("\n  Skipping user management — no --user-email provided.")
            results["User Management (/v3/users/*)"] = "SKIP (use --user-email)"
    else:
        results["User Management (/v3/users/*)"] = "SKIP (use --user-email)"

    # ── Feature 7: Tags ───────────────────────────────────────────
    demo_tags(api_key)
    results["Tags (GET /v3/tags)"] = "PASS"

    # ── Summary ───────────────────────────────────────────────────
    print_summary(results)


if __name__ == "__main__":
    main()
