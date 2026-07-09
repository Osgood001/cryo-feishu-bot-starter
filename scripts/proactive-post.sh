#!/usr/bin/env bash
# Proactively post a Feishu/Lark message through lark-cli.
#
# Usage:
#   scripts/proactive-post.sh --chat oc_xxx "message"
#   scripts/proactive-post.sh --user ou_xxx "message"
#   printf '%s\n' "message" | scripts/proactive-post.sh --chat oc_xxx
set -euo pipefail

MODE="${1:-}"
TARGET="${2:-}"
TEXT="${3:-}"

if [ -z "$TEXT" ] && [ ! -t 0 ]; then
  TEXT="$(cat)"
fi

if [ -z "$MODE" ] || [ -z "$TARGET" ] || [ -z "$TEXT" ]; then
  echo "usage: scripts/proactive-post.sh --chat oc_xxx [text] | --user ou_xxx [text]" >&2
  exit 2
fi

IDENTITY="${LARK_CLI_IDENTITY:-bot}"
PROFILE="${LARK_CLI_PROFILE:-}"
SIG="${BOT_SIGNATURE:-}"

if [ -n "$SIG" ]; then
  TEXT="${TEXT}

${SIG}"
fi

cmd=(lark-cli)
if [ -n "$PROFILE" ]; then
  cmd+=(--profile "$PROFILE")
fi

case "$MODE" in
  --chat)
    exec "${cmd[@]}" im +messages-send --as "$IDENTITY" --chat-id "$TARGET" --markdown "$TEXT" --format json
    ;;
  --user)
    exec "${cmd[@]}" im +messages-send --as "$IDENTITY" --user-id "$TARGET" --markdown "$TEXT" --format json
    ;;
  *)
    echo "usage: --chat | --user" >&2
    exit 2
    ;;
esac
