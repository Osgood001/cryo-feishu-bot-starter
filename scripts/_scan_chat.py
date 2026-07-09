#!/usr/bin/env python3
"""Render lark-cli chat-messages-list JSON into a compact timeline."""

import json
import sys


def sender_name(message: dict) -> str:
    sender = message.get("sender") or {}
    return (
        sender.get("name")
        or sender.get("id")
        or sender.get("sender_type")
        or "unknown"
    )


def clean_content(text: str) -> str:
    return " ".join((text or "").split())


def render_message(message: dict) -> str:
    when = message.get("create_time") or ""
    name = sender_name(message)
    msg_type = message.get("msg_type") or "message"
    content = clean_content(message.get("content", ""))
    if message.get("deleted"):
        content = "[deleted] " + content
    if not content:
        content = f"[{msg_type}]"
    return f"{when} | {name} | {content}"


def main() -> int:
    payload = json.load(sys.stdin)
    messages = payload.get("data", {}).get("messages", [])
    for message in reversed(messages):
        print(render_message(message))
        replies = message.get("thread_replies") or []
        for reply in replies:
            if reply.get("message_id") == message.get("message_id"):
                continue
            print("  " + render_message(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
