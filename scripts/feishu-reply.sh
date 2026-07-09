#!/usr/bin/env bash
# Queue a reply to a specific Feishu/Lark source message.
#
# Usage:
#   scripts/feishu-reply.sh <feishu_chat_id> <feishu_message_id> "reply text"
#   printf '%s\n' "reply text" | scripts/feishu-reply.sh <feishu_chat_id> <feishu_message_id>
#
# A separate bridge should watch FEISHU_OUTBOX_DIR and deliver these files.
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

OUT="${FEISHU_OUTBOX_DIR:-messages/outbox}"
mkdir -p "$OUT"

stamp="$(date +%Y-%m-%dT%H-%M-%S)_$(date +%N)_$$"
tmp="$OUT/.tmp_${stamp}.md"
final="$OUT/${stamp}_reply.md"

{
  echo "---"
  echo "from: agent"
  echo "subject: Reply"
  echo "feishu_chat_id: $CHAT"
  echo "feishu_message_id: $MID"
  echo "---"
  echo
  printf '%s\n' "$TEXT"
} > "$tmp"

mv "$tmp" "$final"
echo "queued reply -> chat=$CHAT msg=$MID file=$(basename "$final")"
