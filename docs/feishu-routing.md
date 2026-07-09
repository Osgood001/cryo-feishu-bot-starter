# Feishu Routing Model

The important design choice is to keep three channels separate.

## 1. Source-message replies

Use this only when answering a Feishu-origin inbox message:

```bash
printf '%s\n' "Reply text" \
  | scripts/feishu-reply.sh <feishu_chat_id> <feishu_message_id>
```

The source message must provide both IDs. The reply bridge uses them to send the
answer into the correct chat/thread.

Why this matters:

- It prevents cross-talk between groups.
- It preserves Feishu thread context.
- It makes every reply auditable.

## 2. Proactive group posts

Use this when there is no source message to reply to, and a group post is
intentional:

```bash
printf '%s\n' "Proactive update" \
  | scripts/proactive-post.sh --chat <chat_id>
```

Examples:

- Daily report.
- Requested public announcement.
- Explicit follow-up in the correct working group.

## 3. Operator-only status

Use this for progress reports, next-wake notes, and ambient summaries:

```bash
printf '%s\n' "Status. Next wake: 2026-01-01T10:30" \
  | scripts/proactive-post.sh --user <operator_open_id>
```

Operator status should not be sent into the source Feishu group by default.

## Multiline messages

Prefer stdin for multiline text or text containing quotes, shell variables, or
backticks:

```bash
cat <<'EOF' | scripts/proactive-post.sh --chat oc_xxx
Line one.
Line two with `literal backticks` and $variables.
EOF
```
