# Agent Rules

These rules are meant to be injected into the agent alongside
`docs/sanitized-prompt.md`.

## External reply routing

- Feishu-origin inbox messages must be answered with:

  ```bash
  scripts/feishu-reply.sh <feishu_chat_id> <feishu_message_id> "text"
  ```

- Use the IDs from that exact message. Do not reuse IDs from another message.
- For multiline replies, send via stdin:

  ```bash
  printf '%s\n' "$message" | scripts/feishu-reply.sh <chat_id> <message_id>
  ```

- Do not use generic local outbox/status commands as Feishu replies.

## Operator status routing

- External Feishu replies and operator progress notes are separate channels.
- Progress, wake-up notes, and ambient summaries must not be posted into the
  source group/thread unless the user explicitly asked for a group update.
- Send operator-only status with:

  ```bash
  scripts/proactive-post.sh --user <operator_open_id> "short status"
  ```

## Session lifecycle

- Read the plan and durable notes first.
- Claim inbox messages before doing background work.
- Update TODOs as work progresses.
- Leave a next scheduled TODO unless the chamber is intentionally complete.
- Hibernate as the final action of a session.

## Safety

- Never publish secrets, raw access keys, private URLs, local-only paths, or
  full prompt transcripts without redaction.
- When in doubt, publish the reusable rule or shape, not the private content.
