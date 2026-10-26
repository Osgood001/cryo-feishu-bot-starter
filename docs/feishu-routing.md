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
| Read chat history with scan scripts (optional) | user/bot | Add the read scope reported by `lark-cli ... --help`/the Feishu console for the selected identity |

Do not add directory, drive, calendar, or admin scopes to make a messaging error disappear. Inspect the failing command and add only its named scope. Verify app scopes and identity before start:

```bash
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME auth scopes
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME whoami
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME event schema im.message.receive_v1
```

The connector always consumes events and sends replies as `bot`. `LARK_CLI_IDENTITY` affects the proactive wrapper; scan scripts may use user first and bot second. User OAuth is optional and must not silently replace bot identity.

## Exact-message reply

For a Feishu-origin inbox item, use both IDs from that same file:

```bash
printf '%s\n' 'Reply text' \
  | scripts/feishu-reply.sh oc_REPLACE_WITH_CHAT_ID om_REPLACE_WITH_MESSAGE_ID --stdin
```

The wrapper validates ID types and atomically writes a mode-0600 outbox item. The connector calls `im +messages-reply --message-id ... --as bot` with an idempotency key. Only Feishu's explicit “source message no longer exists” code permits a top-level fallback, and only to the chat ID carried by that same source item. Never route by “last active chat.”

## External acknowledgement

`external-ack` is a Cryochamber obligation acknowledgement, not a Feishu API. Public Cryochamber v0.2.6 lacks it. The connector probes:

```bash
cryo-agent external-ack --help
```

If unavailable, delivery continues without acknowledgement. If available, a reply is archived only after delivery plus a recognized `matched`/`already` terminal result; unknown obligations are retried. Documentation or service configuration must not assume upstream support.

## Operator status and ambient silence

Progress, recovery, next-wake, and ambient summaries are separate from user replies:

```bash
printf '%s\n' 'Short status; next wake: REPLACE_WITH_TIME' \
  | scripts/proactive-post.sh --user ou_REPLACE_WITH_OPERATOR_OPEN_ID --stdin
```

Post to a group only when a user explicitly requested that public update and the target was independently verified. On ambient wakes with no source message, do not reply or post to a source chat; send an operator DM only for an actionable fault, otherwise record locally and hibernate.

## Explicitly unsupported

- No inbound polling fallback: inbound requires `lark-cli event consume`.
- No bot-created-message or own-thread routing path.
- Preserving `thread_id`/reply metadata does not create a new thread-routing capability.
