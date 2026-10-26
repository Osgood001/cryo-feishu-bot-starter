#!/usr/bin/env bash
# Proactively post a Feishu/Lark message (not a reply) through lark-cli.
# Use it for operator status DMs and explicitly requested announcements only.
#
# Usage:
#   scripts/proactive-post.sh --user "$OPERATOR_OPEN_ID" "short status"
#   scripts/proactive-post.sh --chat oc_xxx "announcement"
#   printf '%s\n' "$text" | scripts/proactive-post.sh --user "$OPERATOR_OPEN_ID" --stdin
#
# Env: LARK_CLI (default lark-cli), LARK_CLI_PROFILE, LARK_CLI_IDENTITY (default bot),
#      BOT_SIGNATURE (optional), DRY_RUN=1 prints the command shape instead of sending.
set -euo pipefail

MODE="${1:-}"
TARGET="${2:-}"
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

if [ -z "$MODE" ] || [ -z "$TARGET" ] || [ -z "$TEXT" ]; then
  echo "usage: scripts/proactive-post.sh --chat oc_xxx [text|--stdin] | --user ou_xxx [text|--stdin]" >&2
  exit 2
fi
if [ "$TEXT" = "--stdin" ]; then
  echo "error: refusing to send literal --stdin" >&2
  exit 2
fi

case "$MODE" in
  --chat) flag=--chat-id; pattern='^oc_[A-Za-z0-9]+$' ;;
  --user) flag=--user-id; pattern='^ou_[A-Za-z0-9]+$' ;;
  *) echo "usage: --chat oc_xxx | --user ou_xxx" >&2; exit 2 ;;
esac
if ! [[ "$TARGET" =~ $pattern ]]; then
  echo "error: target does not match $pattern" >&2
  exit 2
fi

if [ -n "${BOT_SIGNATURE:-}" ]; then
  TEXT="${TEXT}

${BOT_SIGNATURE}"
fi

cmd=("${LARK_CLI:-lark-cli}")
if [ -n "${LARK_CLI_PROFILE:-}" ]; then
  cmd+=(--profile "$LARK_CLI_PROFILE")
fi
cmd+=(im +messages-send --as "${LARK_CLI_IDENTITY:-bot}" "$flag" "$TARGET" --markdown "$TEXT" --format json)

if [ "${DRY_RUN:-0}" = "1" ]; then
  echo "dry-run: ${cmd[0]} ... im +messages-send $flag <target> --markdown <${#TEXT} chars>"
  exit 0
fi
exec "${cmd[@]}"
