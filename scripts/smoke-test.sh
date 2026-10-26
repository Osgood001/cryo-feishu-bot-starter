#!/usr/bin/env bash
# Hermetic end-to-end smoke: exact-ID queue -> fake connector delivery; no network/send.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
tmp="$(mktemp -d)"
cleanup() { rm -rf -- "$tmp"; }
trap cleanup EXIT

export CHAMBER_DIR="$tmp/chamber"
export CONNECTOR_STATE_DIR="$tmp/state"
export FEISHU_OUTBOX_DIR="$CHAMBER_DIR/messages/outbox"
export LARK_CLI="$ROOT/tests/fakes/lark-cli"
export CRYO_AGENT="$ROOT/tests/fakes/cryo-agent"
export FAKE_LARK_LOG="$tmp/lark.jsonl"
export FAKE_CRYO_HELP_RC=2
mkdir -p "$FEISHU_OUTBOX_DIR"

printf '%s\n' 'offline smoke reply' \
  | "$ROOT/scripts/feishu-reply.sh" oc_SmokeChat1 om_SmokeMessage1 --stdin >/dev/null
python3 "$ROOT/connector/feishu_connector.py" once >/dev/null
grep -Fq '"+messages-reply"' "$FAKE_LARK_LOG"
grep -Fq '"om_SmokeMessage1"' "$FAKE_LARK_LOG"

before="$(wc -l <"$FAKE_LARK_LOG")"
DRY_RUN=1 "$ROOT/scripts/proactive-post.sh" --user ou_SmokeOperator1 'offline status' \
  | grep -Fq 'dry-run:'
after="$(wc -l <"$FAKE_LARK_LOG")"
test "$before" = "$after"

echo 'smoke-test: fake-only exact reply=ok proactive dry-run=ok network=none'
