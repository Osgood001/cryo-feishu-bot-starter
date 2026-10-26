#!/usr/bin/env bash
# Render a compact recent timeline for one Feishu/Lark chat.
set -euo pipefail

CHAT="${1:-${DEFAULT_FEISHU_CHAT_ID:-}}"
N="${2:-30}"
DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$CHAT" ]; then
  echo "usage: scripts/scan-chat.sh <chat_id> [count]" >&2
  exit 2
fi

PROFILE="${LARK_CLI_PROFILE:-}"
cmd=("${LARK_CLI:-lark-cli}")
if [ -n "$PROFILE" ]; then
  cmd+=(--profile "$PROFILE")
fi

pull() {
  local as_identity="$1"
  "${cmd[@]}" im +chat-messages-list \
    --chat-id "$CHAT" \
    --as "$as_identity" \
    --order desc \
    --page-size "$N" \
    --no-reactions \
    --format json 2>/dev/null
}

primary="${FEISHU_SCAN_AS_PRIMARY:-user}"
fallback="${FEISHU_SCAN_AS_FALLBACK:-bot}"

OUT="$(pull "$primary" | python3 "$DIR/_scan_chat.py" 2>/dev/null || true)"
if [ -z "$OUT" ] && [ "$fallback" != "$primary" ]; then
  OUT="$(pull "$fallback" | python3 "$DIR/_scan_chat.py" 2>/dev/null || true)"
fi

[ -n "$OUT" ] && printf '%s\n' "$OUT" || echo "(no readable messages)"
