# Cryo Feishu Bot Starter

A small starter kit for running a long-lived AI agent that wakes on a schedule,
handles Feishu/Lark messages, and hibernates cleanly after each session.

This repo is a redacted extraction of an internal Cryochamber + Feishu workflow.
It keeps the reusable operating model and wrapper scripts, but removes project
history, credentials, real open IDs, chat IDs, prompts, and host-specific paths.

Use it together with the standalone Cryochamber scheduler:

- Cryochamber source: https://github.com/Osgood001/cryochamber
- Current practice version: `0.2.6`

## What this gives you

- A prompt contract for a scheduled agent: orient, work, record, schedule, hibernate.
- A Feishu reply model that prevents cross-talk by replying with exact
  `chat_id` + `message_id` pairs from the source message.
- A separate proactive/status channel for operator notes.
- Thin `lark-cli` wrappers for listing chats, scanning chat history, and posting
  proactive messages.
- A practical install/configuration guide for wiring Cryochamber, a coding
  agent, and Feishu/Lark together.
- Redaction and security checklists for publishing agent prompts safely.

## Non-goals

- This does not include Feishu app credentials or a hosted message bridge.
- This does not include any production monitoring, database, or secret manager.
- This does not publish private production prompts, open IDs, chat IDs, access
  keys, message history, or host-specific paths.

## Quick start

1. Install Cryochamber:

   ```bash
   cargo install --git https://github.com/Osgood001/cryochamber --locked
   cryo --version
   cryo-agent --version
   ```

   The versions should match. This starter currently documents `0.2.6`.

2. Install and authenticate `lark-cli` for your Feishu app. Your bot identity
   needs message send/read scopes for group routing; user identity is optional
   unless you need user-only Feishu operations.

3. Create a chamber and copy the starter files:

   ```bash
   mkdir my-feishu-agent
   cd my-feishu-agent
   cryo init --agent codex
   git clone https://github.com/Osgood001/cryo-feishu-bot-starter.git starter
   cp -R starter/scripts starter/docs starter/examples starter/AGENTS.md .
   cp starter/.env.example .env
   ```

4. Fill in `.env`, especially:

   ```bash
   LARK_CLI_PROFILE=your_lark_cli_profile
   LARK_CLI_IDENTITY=bot
   FEISHU_OUTBOX_DIR=messages/outbox
   OPERATOR_OPEN_ID=ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

5. Wire your Feishu inbox bridge to write Feishu-origin messages with frontmatter like
   `examples/inbox-message.md`.

6. Put the hard routing rules from `AGENTS.md` and the workflow in
   `docs/sanitized-prompt.md` into your agent prompt. In Feishu chambers, these
   rules intentionally override Cryochamber's generic local-outbox reply path:
   Feishu user replies go through `scripts/feishu-reply.sh`, while operator
   status goes through `scripts/proactive-post.sh --user`.

7. Start the chamber:

   ```bash
   cryo start --agent codex
   ```

8. In each session the agent should:
   - read the plan and TODOs,
   - inspect or claim inbox messages,
   - answer Feishu messages with `scripts/feishu-reply.sh`,
   - send operator status with `scripts/proactive-post.sh --user ...`,
   - leave a next TODO before hibernating.

See [docs/setup-guide.md](docs/setup-guide.md) for a fuller end-to-end setup
and validation checklist.

## Repository layout

```text
.
├── AGENTS.md                    # Agent-facing hard rules
├── docs/
│   ├── cryochamber-runbook.md   # Session lifecycle
│   ├── feishu-routing.md        # Reply/status routing model
│   ├── redaction-checklist.md   # What to remove before publishing
│   ├── setup-guide.md           # End-to-end install/config guide
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

## Minimal validation

```bash
scripts/list-chats.sh
scripts/scan-chat.sh oc_xxx 5
printf '%s\n' "test reply" | scripts/feishu-reply.sh oc_xxx om_xxx
printf '%s\n' "operator test" | scripts/proactive-post.sh --user ou_xxx
cryo-agent todo add "heartbeat" --at "+30 minutes"
cryo-agent hibernate --summary "setup validation complete"
```

Use real `oc_...` and `om_...` IDs only from a test message you control.

## License

MIT
