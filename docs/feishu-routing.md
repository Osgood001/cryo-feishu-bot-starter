# Feishu app, identity, and routing

## App setup and minimum scopes

Enable bot capability, publish the app to the intended tenant, add it only to intended chats, and subscribe to `im.message.receive_v1` in the Feishu developer console.

Grant only the paths you use:

| Path | Identity | Minimum scope |
|---|---|---|
| Receive direct messages | bot | `im:message.p2p_msg:readonly` |
| Receive group @mentions | bot | `im:message.group_at_msg:readonly` |
| Reply/send as the app | bot | `im:message:send_as_bot` |
| Send as an authorized person (optional) | user | `im:message.send_as_user`, `im:message` |
| Read chat/thread history for context excerpts or scan scripts (optional) | bot/user | Add the read scope reported by `lark-cli ... --help`/the Feishu console for the selected identity |

Do not add directory, drive, calendar, or admin scopes to make a messaging error disappear. Inspect the failing command and add only its named scope. Verify app scopes and identity before start:

```bash
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME auth scopes
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME whoami
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME event schema im.message.receive_v1
```

The connector always consumes events and sends replies as `bot`. `LARK_CLI_IDENTITY` affects the proactive wrapper; scan scripts may use user first and bot second. User OAuth is optional and must not silently replace bot identity.

## Context injection & `@` mention mapping

Every handled inbound event is written to `messages/inbox/*.md` (mode `0600`) with structured frontmatter and system notes so the agent can answer accurately without guessing:

- **Frontmatter metadata:** `feishu_chat_id`, `feishu_message_id`, `feishu_chat_type`, `feishu_sender`, `feishu_sender_name`, `feishu_mentions` (`Name=ou_...`), `feishu_reply_to`, and `feishu_thread_id`.
- **`@` mention resolution:** placeholder keys (such as `@_user_1`) are replaced with `@DisplayName` in the body text; non-bot mentions are listed in both frontmatter and a system note showing `<at user_id="open_id">Name</at>` syntax so replies can mention the right person.
- **Exact reply command hint:** every Feishu inbox file includes the exact `scripts/feishu-reply.sh <feishu_chat_id> <feishu_message_id> --stdin` command bound to that message, plus an explicit reminder not to reuse IDs or use `cryo-agent send`.
- **Optional thread/chat/quote excerpts (`FEISHU_CONTEXT_MESSAGES`):** defaults to `0` (disabled, requiring no read scopes). When set to `1..50` (for example `10`) and bot read scopes are granted, the connector performs best-effort `lark-cli` lookups at inbox write time:
  - Group topic thread (`omt_...`): fetches chronological thread messages via `im +threads-messages-list`.
  - Direct message (`p2p`) or non-thread group: fetches recent messages via `im +chat-messages-list` and reverses them into chronological order.
  - Reply/quote (`feishu_reply_to` / `parent_id`): fetches the quoted parent via `im +messages-mget` so pronouns like "this/that/above" resolve cleanly.
  - Failures, timeouts, or missing read scopes are non-fatal: the inbound message is still written with its exact IDs and reply hint.

## Exact-message reply & reply targeting

For a Feishu-origin inbox item, use both IDs from that same file:

```bash
printf '%s\n' 'Reply text' \
  | scripts/feishu-reply.sh oc_REPLACE_WITH_CHAT_ID om_REPLACE_WITH_MESSAGE_ID --stdin
```

Before sending, verify the reply text matches that exact item (same chat, same thread/quoted parent, same sender, same topic)—never answer one thread with another task's status.

The wrapper validates ID types and atomically writes a mode-0600 outbox item. The connector calls `im +messages-reply --message-id ... --as bot` with an idempotency key. Only Feishu's explicit "source message no longer exists" code permits a top-level fallback, and only to the chat ID carried by that same source item. Never route by "last active chat." Never use `cryo-agent send` or `cryo-agent reply` as a Feishu reply.

## External acknowledgement

`external-ack` is a Cryochamber obligation acknowledgement (paired with `CRYO_EXTERNAL_REPLY_SOURCE=feishu` in Cryochamber builds that support it), not a Feishu API. Public Cryochamber v0.2.6 lacks it. The connector probes:

```bash
cryo-agent external-ack --help
```

If unavailable, delivery continues without acknowledgement. If available, a reply is archived only after delivery plus a recognized `matched`/`already` terminal result; unknown obligations are retried, and an agent waiting on `hibernate` should wait for the connector to finish acknowledging rather than falling back to `cryo-agent send`. Documentation or service configuration must not assume upstream support.

## Operator status and ambient silence

Progress, recovery, next-wake, and ambient summaries are separate from user replies:

```bash
printf '%s\n' 'Short status; next wake: REPLACE_WITH_TIME' \
  | scripts/proactive-post.sh --user ou_REPLACE_WITH_OPERATOR_OPEN_ID --stdin
```

Post to a group only when a user explicitly requested that public update and the target was independently verified. On ambient wakes with no source message, do not reply or post to a source chat; send an operator DM only for an actionable fault, otherwise record locally and hibernate.

## Explicitly unsupported

- No inbound polling fallback: inbound requires `lark-cli event consume` (optional `FEISHU_CONTEXT_MESSAGES` only enriches an event already received over websocket).
- No bot-created-message or own-thread routing path.
- Preserving `thread_id`/reply metadata or injecting thread excerpts does not create a new thread-routing capability.
