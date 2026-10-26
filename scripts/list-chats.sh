#!/usr/bin/env bash
# List group chats visible to the bot as "chat_id<TAB>name".
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
PROFILE="${LARK_CLI_PROFILE:-}"
IDENTITY="${LARK_CLI_IDENTITY:-bot}"

cmd=("${LARK_CLI:-lark-cli}")
if [ -n "$PROFILE" ]; then
  cmd+=(--profile "$PROFILE")
fi

"${cmd[@]}" im +chat-list --as "$IDENTITY" --format json \
  | python3 "$DIR/_list_chats.py"
