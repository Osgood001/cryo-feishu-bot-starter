#!/usr/bin/env python3
"""Print lark-cli chat-list JSON as chat_id<TAB>name."""

import json
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    chats = payload.get("data", {}).get("chats", [])
    for chat in chats:
        if chat.get("chat_mode") not in (None, "group", "topic", "DEFAULT"):
            continue
        chat_id = chat.get("chat_id", "")
        name = chat.get("name", "")
        if chat_id:
            print(f"{chat_id}\t{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
