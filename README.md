# Cryo Feishu Bot Starter

A small starter kit for running a long-lived AI agent that wakes on a schedule,
handles Feishu/Lark messages, and hibernates cleanly after each session.

This repo is a redacted extraction of an internal Cryochamber + Feishu workflow.
It keeps the reusable operating model and wrapper scripts, but removes project
history, credentials, real open IDs, chat IDs, prompts, and host-specific paths.

## What this gives you

- A prompt contract for a scheduled agent: orient, work, record, schedule, hibernate.
- A Feishu reply model that prevents cross-talk by replying with exact
  `chat_id` + `message_id` pairs from the source message.
- A separate proactive/status channel for operator notes.
- Thin `lark-cli` wrappers for listing chats, scanning chat history, and posting
  proactive messages.
- Redaction and security checklists for publishing agent prompts safely.

## Non-goals

- This does not include a full scheduler daemon implementation.
- This does not include Feishu app credentials or a hosted message bridge.
- This does not include any production monitoring, database, or secret manager.

## Quick start

1. Install and authenticate `lark-cli` for your Feishu app.
2. Copy `.env.example` to `.env` and fill in local values.
3. Wire your inbox bridge to write Feishu-origin messages with frontmatter like
   `examples/inbox-message.md`.
4. Configure your scheduler to inject the prompt in `docs/sanitized-prompt.md`.
5. Run a session. The agent should:
   - read the plan and TODOs,
   - claim inbox messages,
   - answer Feishu messages with `scripts/feishu-reply.sh`,
   - send operator status with `scripts/proactive-post.sh --user ...`,
   - leave a next TODO before hibernating.

## Repository layout

```text
.
├── AGENTS.md                    # Agent-facing hard rules
├── docs/
│   ├── cryochamber-runbook.md   # Session lifecycle
│   ├── feishu-routing.md        # Reply/status routing model
│   ├── redaction-checklist.md   # What to remove before publishing
│   ├── sanitized-prompt.md      # Prompt template with placeholders
│   └── security.md              # Operational safety notes
├── examples/
│   ├── inbox-message.md         # Feishu-origin message example
│   └── outbox-reply.md          # Routed reply file example
├── scripts/
│   ├── feishu-reply.sh          # Queue exact-message replies
│   ├── proactive-post.sh        # Post proactive/operator messages
│   ├── list-chats.sh            # List group chats visible to the bot
│   ├── scan-all.sh              # Scan recent messages across chats
│   ├── scan-chat.sh             # Scan one chat timeline
│   ├── _list_chats.py
│   └── _scan_chat.py
└── messages/
    ├── inbox/.gitkeep
    └── outbox/.gitkeep
```

## Core rule

Do not use a local/operator outbox as a Feishu reply. A Feishu-origin message
must be answered with the exact `feishu_chat_id` and `feishu_message_id` from
that message:

```bash
printf '%s\n' "Reply text" \
  | scripts/feishu-reply.sh oc_xxx om_xxx
```

Operator status is a different channel:

```bash
printf '%s\n' "Short status, next wake: 2026-01-01T10:30" \
  | scripts/proactive-post.sh --user ou_operator_xxx
```

## License

MIT
