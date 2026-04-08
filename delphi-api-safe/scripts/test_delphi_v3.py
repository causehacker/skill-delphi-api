#!/usr/bin/env python3
import argparse
import json
import shlex
import subprocess
from typing import Any, Dict, List, Optional, Tuple

BASE = "https://api.delphi.ai/v3"


def run(cmd: str) -> str:
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return (p.stdout or "") + ("" if p.returncode == 0 else ("\n" + (p.stderr or "")))


def http_json(method: str, path: str, api_key: str, payload: Optional[dict] = None, stream: bool = False, max_time: int = 25) -> Tuple[str, str]:
    data = ""
    if payload is not None:
        data = f" -d {shlex.quote(json.dumps(payload))}"
    stream_flag = "-N " if stream else ""
    cmd = (
        f"curl -sS {stream_flag}--max-time {max_time} -w '\\nHTTP_STATUS:%{{http_code}}' -X {method} '{BASE}{path}' "
        f"-H 'x-api-key: {api_key}' -H 'Content-Type: application/json'{data}"
    )
    raw = run(cmd)
    if "HTTP_STATUS:" not in raw:
        return "000", raw.strip()
    body, status = raw.rsplit("HTTP_STATUS:", 1)
    return status.strip(), body.strip()


def http_binary(method: str, path: str, api_key: str, payload: Optional[dict] = None, max_time: int = 30) -> Tuple[str, int]:
    """Make an HTTP request expecting binary response. Returns (status, byte_count)."""
    data = ""
    if payload is not None:
        data = f" -d {shlex.quote(json.dumps(payload))}"
    cmd = (
        f"curl -sS --max-time {max_time} -w '\\nHTTP_STATUS:%{{http_code}}' -o /tmp/delphi_voice_test.bin -X {method} '{BASE}{path}' "
        f"-H 'x-api-key: {api_key}' -H 'Content-Type: application/json'{data}"
    )
    raw = run(cmd)
    if "HTTP_STATUS:" not in raw:
        return "000", 0
    _, status = raw.rsplit("HTTP_STATUS:", 1)
    status = status.strip()
    # Count bytes in output file
    try:
        import os
        byte_count = os.path.getsize("/tmp/delphi_voice_test.bin")
    except Exception:
        byte_count = 0
    return status, byte_count


def test_clone(api_key: str) -> Dict[str, Any]:
    """Discover clone identity via GET /v3/clone."""
    c_status, c_body = http_json("GET", "/clone", api_key)
    if c_status == "200":
        try:
            raw = json.loads(c_body)
            # Response may wrap in a "clone" key or be flat
            data = raw.get("clone", raw) if isinstance(raw, dict) else raw
            return {
                "clone": "PASS",
                "clone_http": c_status,
                "clone_name": data.get("name", "Unknown"),
                "clone_data": {k: data.get(k, "") for k in ("name", "slug", "description", "headline", "purpose", "initial_message")},
            }
        except Exception:
            return {
                "clone": "PASS",
                "clone_http": c_status,
                "clone_name": "Unknown",
                "clone_data": {},
            }
    return {
        "clone": "FAIL",
        "clone_http": c_status,
        "clone_name": None,
        "clone_body": c_body[:240],
    }


def test_chat(api_key: str, message: str) -> Dict[str, Any]:
    c_status, c_body = http_json("POST", "/conversation", api_key, {})
    cid = None
    if c_status == "200":
        try:
            cid = json.loads(c_body).get("conversation_id")
        except Exception:
            cid = None

    if not cid:
        return {
            "conversation": "FAIL",
            "stream": "FAIL",
            "overall": "FAIL",
            "note": f"conversation http {c_status}",
            "conversation_http": c_status,
            "stream_http": "-",
            "conversation_id": None,
            "conversation_body": c_body[:240],
        }

    s_status, s_body = http_json(
        "POST",
        "/stream",
        api_key,
        {"message": message, "conversation_id": cid},
        stream=True,
    )
    s_ok = s_status == "200" and "data:" in s_body and "[DONE]" in s_body
    return {
        "conversation": "PASS",
        "stream": "PASS" if s_ok else "FAIL",
        "overall": "PASS" if s_ok else "FAIL",
        "note": "" if s_ok else (f"stream http {s_status}" if s_status != "200" else "stream format error"),
        "conversation_http": c_status,
        "stream_http": s_status,
        "conversation_id": cid,
        "stream_preview": s_body[:280],
    }


def test_voice(api_key: str, message: str) -> Dict[str, Any]:
    """Test voice streaming via POST /v3/voice/stream."""
    # Need a conversation_id first
    c_status, c_body = http_json("POST", "/conversation", api_key, {})
    cid = None
    if c_status == "200":
        try:
            cid = json.loads(c_body).get("conversation_id")
        except Exception:
            cid = None

    if not cid:
        return {
            "voice": "FAIL",
            "voice_http": "-",
            "note": f"could not create conversation (http {c_status})",
            "byte_count": 0,
        }

    v_status, byte_count = http_binary(
        "POST",
        "/voice/stream",
        api_key,
        {"message": message, "conversation_id": cid},
        max_time=30,
    )

    # Voice is PASS if we got 200 and received some PCM data (at least 4800 bytes = 0.1s of audio)
    v_ok = v_status == "200" and byte_count >= 4800
    return {
        "voice": "PASS" if v_ok else "FAIL",
        "voice_http": v_status,
        "byte_count": byte_count,
        "duration_estimate": f"{byte_count / 48000:.1f}s" if byte_count > 0 else "0s",
        "note": "" if v_ok else (f"voice http {v_status}" if v_status != "200" else f"too few bytes ({byte_count})"),
    }


def test_synthesize(api_key: str) -> Dict[str, Any]:
    """Test TTS synthesis via POST /v3/voice/synthesize (batch mode — returns base64 JSON)."""
    s_status, s_body = http_json(
        "POST",
        "/voice/synthesize",
        api_key,
        {"text": "Hello, this is a test of the synthesis endpoint."},
        max_time=30,
    )
    has_audio = False
    if s_status == "200":
        try:
            data = json.loads(s_body)
            audio_b64 = data.get("audio", "")
            has_audio = len(audio_b64) > 100  # base64 PCM should be substantial
        except Exception:
            pass

    s_ok = s_status == "200" and has_audio
    return {
        "synthesize": "PASS" if s_ok else "FAIL",
        "synthesize_http": s_status,
        "has_audio": has_audio,
        "note": "" if s_ok else (f"synthesize http {s_status}" if s_status != "200" else "no audio in response"),
    }


def test_append_clone_message(api_key: str, conversation_id: str) -> Dict[str, Any]:
    """Test appending a clone message via POST /v3/conversation/{id}/append-clone-message."""
    a_status, a_body = http_json(
        "POST",
        f"/conversation/{conversation_id}/append-clone-message",
        api_key,
        {"text": "This is an automated test message injected via the API."},
    )
    has_message_id = False
    if a_status == "200":
        try:
            data = json.loads(a_body)
            has_message_id = bool(data.get("message_id"))
        except Exception:
            pass

    a_ok = a_status == "200" and has_message_id
    return {
        "append_clone_message": "PASS" if a_ok else "FAIL",
        "append_clone_message_http": a_status,
        "has_message_id": has_message_id,
        "note": "" if a_ok else (f"append http {a_status}" if a_status != "200" else "no message_id in response"),
        "preview": a_body[:240],
    }


def test_list_conversations(api_key: str, user_email: str) -> Dict[str, Any]:
    """Test listing conversations via GET /v3/conversation/list?email=..."""
    from urllib.parse import quote
    st, body = http_json("GET", f"/conversation/list?email={quote(user_email)}", api_key)
    conversations = []
    if st == "200":
        try:
            data = json.loads(body)
            conversations = data.get("conversations", [])
        except Exception:
            pass

    ok = st == "200" and isinstance(conversations, list)
    return {
        "list_conversations": "PASS" if ok else "FAIL",
        "list_conversations_http": st,
        "conversation_count": len(conversations),
        "preview": [{"id": c.get("id", ""), "title": c.get("title", "")} for c in conversations[:3]],
        "note": "" if ok else (f"list conversations http {st}" if st != "200" else "unexpected response format"),
    }


def test_conversation_history(api_key: str, conversation_id: str) -> Dict[str, Any]:
    """Test getting conversation history via GET /v3/conversation/{id}/history."""
    st, body = http_json("GET", f"/conversation/{conversation_id}/history?include_citations=true", api_key)
    messages = []
    if st == "200":
        try:
            data = json.loads(body)
            messages = data.get("messages", [])
        except Exception:
            pass

    ok = st == "200" and isinstance(messages, list) and len(messages) > 0
    return {
        "conversation_history": "PASS" if ok else "FAIL",
        "conversation_history_http": st,
        "message_count": len(messages),
        "senders": list(set(m.get("sender", "") for m in messages)),
        "note": "" if ok else (f"history http {st}" if st != "200" else "no messages in response"),
    }


def test_update_conversation_title(api_key: str, conversation_id: str) -> Dict[str, Any]:
    """Test updating conversation title via PUT /v3/conversation/{id}/title."""
    st, body = http_json(
        "PUT",
        f"/conversation/{conversation_id}/title",
        api_key,
        {"title": "API Test Conversation"},
    )
    has_title = False
    if st == "200":
        try:
            data = json.loads(body)
            has_title = bool(data.get("title"))
        except Exception:
            pass

    ok = st == "200" and has_title
    return {
        "update_title": "PASS" if ok else "FAIL",
        "update_title_http": st,
        "note": "" if ok else (f"update title http {st}" if st != "200" else "no title in response"),
        "preview": body[:180],
    }


def test_delete_conversation(api_key: str, conversation_id: str) -> Dict[str, Any]:
    """Test soft-deleting a conversation via DELETE /v3/conversation/{id}."""
    st, body = http_json("DELETE", f"/conversation/{conversation_id}", api_key)
    ok = st == "200"
    return {
        "delete_conversation": "PASS" if ok else "FAIL",
        "delete_conversation_http": st,
        "note": "" if ok else f"delete conversation http {st}",
        "preview": body[:180],
    }


def test_questions(api_key: str) -> Dict[str, Any]:
    """Test getting suggested questions via GET /v3/questions."""
    st, body = http_json("GET", "/questions?type=all&count=5", api_key)
    questions = []
    if st == "200":
        try:
            data = json.loads(body)
            questions = data.get("questions", [])
        except Exception:
            pass

    ok = st == "200" and isinstance(questions, list)
    return {
        "questions": "PASS" if ok else "FAIL",
        "questions_http": st,
        "question_count": len(questions),
        "sample": [q.get("question", "")[:80] for q in questions[:3]],
        "note": "" if ok else (f"questions http {st}" if st != "200" else "unexpected response format"),
    }


def test_list_users(api_key: str) -> Dict[str, Any]:
    """Test paginated user list via GET /v3/users."""
    st, body = http_json("GET", "/users?limit=5", api_key)
    users = []
    has_more = False
    if st == "200":
        try:
            data = json.loads(body)
            users = data.get("users", [])
            has_more = data.get("has_more", False)
        except Exception:
            pass

    ok = st == "200" and isinstance(users, list)
    return {
        "list_users": "PASS" if ok else "FAIL",
        "list_users_http": st,
        "user_count": len(users),
        "has_more": has_more,
        "sample": [{"id": u.get("user_id", ""), "email": u.get("email", "")} for u in users[:3]],
        "note": "" if ok else (f"list users http {st}" if st != "200" else "unexpected response format"),
    }


def test_search_query(api_key: str, query: str) -> Dict[str, Any]:
    """Test knowledge base search via POST /v3/search/query."""
    s_status, s_body = http_json(
        "POST", "/search/query", api_key,
        {"query": [query], "limit": 3},
    )
    chunks = []
    content = []
    if s_status == "200":
        try:
            data = json.loads(s_body)
            chunks = data.get("chunks", [])
            content = data.get("content", [])
        except Exception:
            pass

    s_ok = s_status == "200" and isinstance(chunks, list)
    return {
        "search_query": "PASS" if s_ok else "FAIL",
        "search_query_http": s_status,
        "chunk_count": len(chunks),
        "content_count": len(content),
        "preview": chunks[0]["text"][:200] if chunks else "",
        "note": "" if s_ok else (f"search/query http {s_status}" if s_status != "200" else "unexpected response format"),
    }


def test_search_content(api_key: str, query: str) -> Dict[str, Any]:
    """Test content source search via POST /v3/search/content."""
    s_status, s_body = http_json(
        "POST", "/search/content", api_key,
        {"query": [query]},
    )
    content = []
    if s_status == "200":
        try:
            data = json.loads(s_body)
            content = data.get("content", [])
        except Exception:
            pass

    s_ok = s_status == "200" and isinstance(content, list)
    return {
        "search_content": "PASS" if s_ok else "FAIL",
        "search_content_http": s_status,
        "content_count": len(content),
        "titles": [c.get("title", "") for c in content[:5]],
        "note": "" if s_ok else (f"search/content http {s_status}" if s_status != "200" else "unexpected response format"),
    }


def test_user_endpoints(api_key: str, user_id: str, allow_write: bool, tag_name: Optional[str], info_text: Optional[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    for label, path in [
        ("flywheel", f"/users/{user_id}/flywheel"),
        ("tier", f"/users/{user_id}/tier"),
        ("usage", f"/users/{user_id}/usage"),
        ("info_get", f"/users/{user_id}/info"),
    ]:
        st, body = http_json("GET", path, api_key)
        out[label] = {"http": st, "pass": st == "200", "preview": body[:180]}

    if allow_write:
        st, body = http_json("PATCH", f"/users/{user_id}", api_key, {"name": "API Test User"})
        out["user_patch_name"] = {"http": st, "pass": st == "200", "preview": body[:180]}

        st, body = http_json("POST", f"/users/{user_id}/revoke", api_key, {})
        out["user_revoke"] = {"http": st, "pass": st == "200", "preview": body[:180]}

        st, body = http_json("POST", f"/users/{user_id}/activate", api_key, {})
        out["user_activate"] = {"http": st, "pass": st == "200", "preview": body[:180]}

        if tag_name:
            st, body = http_json("POST", f"/users/{user_id}/tags/{tag_name}", api_key, {})
            out["user_tag"] = {"http": st, "pass": st == "200", "preview": body[:180]}

            st, body = http_json("DELETE", f"/users/{user_id}/tags/{tag_name}", api_key)
            out["user_untag"] = {"http": st, "pass": st == "200", "preview": body[:180]}

        if info_text:
            st, body = http_json(
                "POST",
                f"/users/{user_id}/info",
                api_key,
                {"info": info_text, "info_type": "JOURNAL"},
            )
            info_id = None
            if st == "200":
                try:
                    info_id = json.loads(body).get("id")
                except Exception:
                    info_id = None
            out["info_create"] = {"http": st, "pass": st == "200", "preview": body[:180], "info_id": info_id}
            if info_id:
                dst, dbody = http_json("DELETE", f"/users/{user_id}/info/{info_id}", api_key)
                out["info_delete"] = {"http": dst, "pass": dst == "200", "preview": dbody[:180]}

    return out


def test_lookup_and_tags(api_key: str, user_email: Optional[str], allow_write: bool, tag_name: Optional[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    user_id = None

    if user_email:
        st, body = http_json("POST", "/users/lookup", api_key, {"email": user_email})
        out["user_lookup"] = {"http": st, "pass": st == "200", "preview": body[:180]}
        if st == "200":
            try:
                user_id = json.loads(body).get("user_id")
            except Exception:
                user_id = None

    st, body = http_json("GET", "/tags", api_key)
    out["tags_get"] = {"http": st, "pass": st == "200", "preview": body[:180]}

    if allow_write and tag_name:
        st, body = http_json("POST", "/tags", api_key, {"name": tag_name, "color": "#3B82F6"})
        out["tags_create"] = {"http": st, "pass": st == "200", "preview": body[:180]}

    out["derived_user_id"] = user_id
    return out


def summarize(result: Dict[str, Any]) -> Dict[str, Any]:
    checks = []
    for k, v in result.items():
        if isinstance(v, dict) and "pass" in v:
            checks.append(bool(v["pass"]))
    overall = "PASS" if checks and all(checks) else ("FAIL" if checks else "UNKNOWN")
    return {"overall": overall, "checks": len(checks), "passed": sum(1 for x in checks if x)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Delphi V3 tester (clone + chat + voice + search + users + tags + info + conversations + questions)")
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--account", default="Account")
    ap.add_argument("--message", default="Please answer in one short sentence to test stream.")
    ap.add_argument("--mode", choices=["chat", "full"], default="chat")
    ap.add_argument("--user-email", help="Required for /users/lookup and /conversation/list")
    ap.add_argument("--user-id", help="Optional user_id. If omitted, derived from lookup when user_email is provided")
    ap.add_argument("--tag-name", help="Tag name for tag/untag tests (required for write tag tests)")
    ap.add_argument("--info-text", help="Text for user info create/delete test")
    ap.add_argument("--allow-write", action="store_true", help="Enable write endpoints (PUT/PATCH/POST/DELETE)")
    ap.add_argument("--test-voice", action="store_true", help="Include voice streaming test")
    ap.add_argument("--test-search", action="store_true", help="Include knowledge base search tests")
    ap.add_argument("--search-query", default="What is your background?", help="Query string for search tests")
    args = ap.parse_args()

    output: Dict[str, Any] = {"account": args.account, "mode": args.mode}

    # Always discover clone identity first
    output["clone"] = test_clone(args.api_key)

    # Always test questions (read-only, available to all clones)
    output["questions"] = test_questions(args.api_key)

    # Always test list users (read-only)
    output["list_users"] = test_list_users(args.api_key)

    if args.mode in ("chat", "full"):
        output["chat"] = test_chat(args.api_key, args.message)
        chat_cid = output["chat"].get("conversation_id") if "chat" in output else None

        # Test conversation history if we got a conversation_id
        if chat_cid:
            output["conversation_history"] = test_conversation_history(args.api_key, chat_cid)

        # Test conversation list if we have a user email
        if args.user_email:
            output["list_conversations"] = test_list_conversations(args.api_key, args.user_email)

        # Write-dependent conversation tests
        if chat_cid and args.allow_write:
            output["append_clone_message"] = test_append_clone_message(args.api_key, chat_cid)
            output["update_title"] = test_update_conversation_title(args.api_key, chat_cid)
            # Delete conversation last (soft-delete)
            output["delete_conversation"] = test_delete_conversation(args.api_key, chat_cid)

    # Voice tests (optional, since not all clones have voice)
    if args.test_voice:
        output["voice"] = test_voice(args.api_key, args.message)
        output["synthesize"] = test_synthesize(args.api_key)

    # Search tests (optional, requires Immortal plan)
    if args.test_search:
        output["search_query"] = test_search_query(args.api_key, args.search_query)
        output["search_content"] = test_search_content(args.api_key, args.search_query)

    if args.mode == "full":
        lookup_tags = test_lookup_and_tags(args.api_key, args.user_email, args.allow_write, args.tag_name)
        output["lookup_tags"] = lookup_tags

        user_id = args.user_id or lookup_tags.get("derived_user_id")
        if user_id:
            output["users"] = test_user_endpoints(args.api_key, user_id, args.allow_write, args.tag_name, args.info_text)
        else:
            output["users"] = {
                "note": "Skipped user endpoint checks because no user_id available. Provide --user-id or --user-email."
            }

    # summaries
    if "clone" in output:
        c = output["clone"]
        output["clone_summary"] = {
            "overall": c.get("clone", "UNKNOWN"),
            "clone_http": c.get("clone_http"),
            "clone_name": c.get("clone_name"),
        }

    if "chat" in output:
        c = output["chat"]
        output["chat_summary"] = {
            "overall": c.get("overall", "UNKNOWN"),
            "conversation_http": c.get("conversation_http"),
            "stream_http": c.get("stream_http"),
        }

    if "voice" in output:
        v = output["voice"]
        output["voice_summary"] = {
            "overall": v.get("voice", "UNKNOWN"),
            "voice_http": v.get("voice_http"),
            "byte_count": v.get("byte_count"),
            "duration_estimate": v.get("duration_estimate"),
        }

    if "synthesize" in output:
        s = output["synthesize"]
        output["synthesize_summary"] = {
            "overall": s.get("synthesize", "UNKNOWN"),
            "synthesize_http": s.get("synthesize_http"),
            "has_audio": s.get("has_audio"),
        }

    if "append_clone_message" in output:
        acm = output["append_clone_message"]
        output["append_clone_message_summary"] = {
            "overall": acm.get("append_clone_message", "UNKNOWN"),
            "append_clone_message_http": acm.get("append_clone_message_http"),
        }

    if "questions" in output:
        q = output["questions"]
        output["questions_summary"] = {
            "overall": q.get("questions", "UNKNOWN"),
            "questions_http": q.get("questions_http"),
            "question_count": q.get("question_count"),
        }

    if "list_users" in output:
        lu = output["list_users"]
        output["list_users_summary"] = {
            "overall": lu.get("list_users", "UNKNOWN"),
            "list_users_http": lu.get("list_users_http"),
            "user_count": lu.get("user_count"),
            "has_more": lu.get("has_more"),
        }

    if "list_conversations" in output:
        lc = output["list_conversations"]
        output["list_conversations_summary"] = {
            "overall": lc.get("list_conversations", "UNKNOWN"),
            "list_conversations_http": lc.get("list_conversations_http"),
            "conversation_count": lc.get("conversation_count"),
        }

    if "conversation_history" in output:
        ch = output["conversation_history"]
        output["conversation_history_summary"] = {
            "overall": ch.get("conversation_history", "UNKNOWN"),
            "conversation_history_http": ch.get("conversation_history_http"),
            "message_count": ch.get("message_count"),
        }

    if "update_title" in output:
        ut = output["update_title"]
        output["update_title_summary"] = {
            "overall": ut.get("update_title", "UNKNOWN"),
            "update_title_http": ut.get("update_title_http"),
        }

    if "delete_conversation" in output:
        dc = output["delete_conversation"]
        output["delete_conversation_summary"] = {
            "overall": dc.get("delete_conversation", "UNKNOWN"),
            "delete_conversation_http": dc.get("delete_conversation_http"),
        }

    if "search_query" in output:
        sq = output["search_query"]
        output["search_query_summary"] = {
            "overall": sq.get("search_query", "UNKNOWN"),
            "search_query_http": sq.get("search_query_http"),
            "chunk_count": sq.get("chunk_count"),
        }

    if "search_content" in output:
        sc = output["search_content"]
        output["search_content_summary"] = {
            "overall": sc.get("search_content", "UNKNOWN"),
            "search_content_http": sc.get("search_content_http"),
            "content_count": sc.get("content_count"),
        }

    if "lookup_tags" in output:
        output["lookup_tags_summary"] = summarize(output["lookup_tags"])
    if "users" in output and isinstance(output["users"], dict):
        output["users_summary"] = summarize(output["users"])

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
