#!/usr/bin/env bash
# Print a compact recent timeline for every group chat visible to the bot.
set -euo pipefail

N="${1:-20}"
DIR="$(cd "$(dirname "$0")" && pwd)"

"$DIR/list-chats.sh" | while IFS=$'\t' read -r cid cname; do
  [ -z "$cid" ] && continue
  echo "===== chat: $cname ($cid) ====="
  "$DIR/scan-chat.sh" "$cid" "$N"
  echo
done
