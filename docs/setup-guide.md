# Setup Guide

This guide turns the starter repo into a working Feishu/Lark agent chamber.
It assumes Linux or macOS, a coding agent such as Codex/Claude/OpenCode, and a
Feishu app that can read/send messages through `lark-cli`.

## Architecture

The production pattern has four pieces:

1. **Cryochamber** runs the lifecycle: schedule, wake, inject prompt, track
   TODOs, and hibernate.
2. **Coding agent** does the work inside each session.
3. **Feishu bridge** writes inbound Feishu messages into `messages/inbox/` and
   delivers reply files from `messages/outbox/`.
4. **Wrapper scripts** keep routing explicit:
   - `scripts/feishu-reply.sh` writes a reply tied to one source
     `feishu_chat_id` + `feishu_message_id`.
   - `scripts/proactive-post.sh` intentionally posts to a chosen group or user.
   - `scripts/scan-chat.sh`, `scripts/scan-all.sh`, and `scripts/list-chats.sh`
     inspect Feishu context through `lark-cli`.

## 1. Install Cryochamber

Install the current practice version from the standalone repository:

```bash
cargo install --git https://github.com/Osgood001/cryochamber --locked
cryo --version
cryo-agent --version
```

Both commands should report the same version. This starter is written against
`0.2.6`.

If you prefer to build from a checked-out source tree:

```bash
git clone https://github.com/Osgood001/cryochamber.git
cd cryochamber
cargo install --path . --locked
```

## 2. Create the chamber directory

```bash
mkdir my-feishu-agent
cd my-feishu-agent
cryo init --agent codex
```

You can use another agent command:

```bash
cryo init --agent claude
cryo init --agent opencode
```

Check `cryo.toml` after init. The important default for Feishu integration is:

```toml
watch_dirs = ["messages/inbox"]
```

That makes new inbox files wake the chamber.

## 3. Add the Feishu starter files

```bash
git clone https://github.com/Osgood001/cryo-feishu-bot-starter.git starter
cp -R starter/scripts starter/docs starter/examples starter/AGENTS.md .
cp starter/.env.example .env
mkdir -p messages/inbox messages/outbox
```

Edit `.env`:

```bash
LARK_CLI_PROFILE=your_lark_cli_profile
LARK_CLI_IDENTITY=bot
BOT_SIGNATURE="sent by your agent"
FEISHU_OUTBOX_DIR=messages/outbox
OPERATOR_OPEN_ID=ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
DEFAULT_FEISHU_CHAT_ID=oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Do not commit `.env`.

## 4. Authenticate `lark-cli`

Install `lark-cli` following its own documentation, then authenticate the Feishu
app profile you will use for this bot.

Validate read/send access:

```bash
scripts/list-chats.sh
scripts/scan-chat.sh <oc_test_chat_id> 5
printf '%s\n' "operator test" \
  | scripts/proactive-post.sh --user <ou_operator_open_id>
```

Use a test chat or private operator account first.

## 5. Wire inbound messages

Your Feishu event bridge should write each inbound message to `messages/inbox/`
as Markdown with YAML frontmatter:

```markdown
---
from: Feishu user
source: feishu
feishu_chat_id: oc_xxx
feishu_message_id: om_xxx
feishu_sender: ou_xxx
feishu_sender_name: Example User
feishu_thread_id: "(none)"
---

Message text here.

Reply with:
scripts/feishu-reply.sh oc_xxx om_xxx "<text>"
```

The bridge can be simple: webhook handler in, Markdown file out. The key
requirement is that each file carries the exact `oc_...` chat ID and `om_...`
message ID from the source message.

## 6. Wire outbound replies

`scripts/feishu-reply.sh` writes a routed reply file under `messages/outbox/`.
Your bridge should watch that directory, parse frontmatter, and call Feishu to
reply to the source message.

The bridge must not route by "last active chat". It should route only by:

```yaml
feishu_chat_id: oc_xxx
feishu_message_id: om_xxx
```

Proactive posts do not use the outbox bridge. They call `lark-cli` directly:

```bash
printf '%s\n' "public update" | scripts/proactive-post.sh --chat oc_xxx
printf '%s\n' "private status" | scripts/proactive-post.sh --user ou_xxx
```

## 7. Update the agent prompt

Add `AGENTS.md` and `docs/sanitized-prompt.md` to the prompt you give the
coding agent.

Important Feishu override:

- Generic Cryochamber docs use `cryo-agent send` for local operator messages.
- A Feishu chamber must not use that local outbox as a Feishu reply.
- Feishu-origin messages are answered only with `scripts/feishu-reply.sh`.
- Progress and wake-up notes go only to the operator with
  `scripts/proactive-post.sh --user`.

This separation is the main protection against cross-talk between groups.

## 8. Start and test

Start the chamber:

```bash
cryo start --agent codex
```

Send a controlled Feishu test message that mentions the bot or otherwise enters
the inbox bridge. Confirm:

1. A file appears in `messages/inbox/`.
2. Cryochamber wakes the agent.
3. The agent uses `scripts/feishu-reply.sh` with the message's own IDs.
4. Your bridge delivers the matching outbox reply to Feishu.
5. The session ends with a pending TODO and `cryo-agent hibernate`.

Useful checks:

```bash
cryo status
cryo log
cryo-agent todo list
```

## Safety checklist

Before publishing or sharing your own derived starter:

- Replace real `oc_...`, `om_...`, and `ou_...` IDs with placeholders.
- Remove access keys, webhook secrets, bearer tokens, and local paths.
- Remove private conversation history.
- Keep only reusable prompt rules, not private project instructions.
- Run a secret scan:

  ```bash
  rg -n "Bearer|Authorization|accessKey|secret|token|password|AK|SK|OPENAI|ANTHROPIC|BOHRIUM" .
  ```

## Common mistakes

- Replying through a local/operator outbox instead of exact Feishu IDs.
- Posting status updates into the group where a user asked a question.
- Forgetting to quote relative TODO times:

  ```bash
  cryo-agent todo add "check inbox" --at "+30 minutes"
  ```

- Letting the bridge route by the last active chat.
- Committing `.env`, prompt transcripts, or real message archives.
