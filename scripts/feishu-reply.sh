#!/usr/bin/env bash
# Queue a reply to one exact Feishu/Lark source message.
#
# Usage:
#   scripts/feishu-reply.sh <feishu_chat_id> <feishu_message_id> "reply text"
#   printf '%s\n' "$reply" | scripts/feishu-reply.sh <feishu_chat_id> <feishu_message_id> --stdin
#
# Both IDs must come from the frontmatter of the inbox message being answered.
# The connector (connector/feishu_connector.py) delivers files from the outbox.
set -euo pipefail

CHAT="${1:-}"
MID="${2:-}"
TEXT="${3:-}"

if [ "$TEXT" = "--stdin" ]; then
  if [ -t 0 ]; then
    echo "error: --stdin requires piped or heredoc input" >&2
    exit 2
  fi
  TEXT="$(cat)"
elif [ -z "$TEXT" ] && [ ! -t 0 ]; then
  TEXT="$(cat)"
fi

if [ -z "$CHAT" ] || [ -z "$MID" ] || [ -z "$TEXT" ]; then
  echo "usage: scripts/feishu-reply.sh <chat_id> <message_id> [text|--stdin]" >&2
  exit 2
fi
if [ "$TEXT" = "--stdin" ]; then
  echo "error: refusing to send literal --stdin" >&2
  exit 2
fi
if ! [[ "$CHAT" =~ ^oc_[A-Za-z0-9]+$ ]]; then
  echo "error: chat id must look like oc_... (copy feishu_chat_id from the inbox message)" >&2
  exit 2
fi
if ! [[ "$MID" =~ ^om_[A-Za-z0-9]+$ ]]; then
  echo "error: message id must look like om_... (copy feishu_message_id from the inbox message)" >&2
  exit 2
fi

OUT="${FEISHU_OUTBOX_DIR:-messages/outbox}"
umask 077
mkdir -p "$OUT"

stamp="$(date +%Y-%m-%dT%H-%M-%S)_$(date +%N)_$$"
tmp="$OUT/.tmp_${stamp}.md"
final="$OUT/${stamp}_reply.md"

{
  echo "---"
  echo "from: agent"
  echo "source: feishu"
  echo "subject: Reply"
  echo "feishu_chat_id: $CHAT"
  echo "feishu_message_id: $MID"
  echo "---"
  echo
  printf '%s\n' "$TEXT"
} > "$tmp"

# Atomic rename: the connector never sees a half-written file.
mv "$tmp" "$final"
echo "queued reply file=$(basename "$final")"
