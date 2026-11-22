# Agent Rules

These rules are meant to be injected into the agent alongside
`docs/sanitized-prompt.md`.

## Fast first reply

- Right after claiming inbox messages (`cryo-agent receive`), **before** reading
  `plan.md`, durable notes, or starting deep exploration, triage every
  Feishu-origin message:
  - If you can answer within **2 quick tool calls**, send the full answer now
    via `scripts/feishu-reply.sh`.
  - Otherwise, immediately send a short receipt (what you will check and a
    rough ETA) via `scripts/feishu-reply.sh`, then finish the real answer in
    the same session or split long work across sessions with a bounded TODO.
- Never let a received Feishu message sit unanswered for 10+ minutes while
  running deep research or background tasks.

## External reply routing & reply targeting

- Feishu-origin inbox messages must be answered **only** with:

  ```bash
  printf '%s\n' "$message" \
    | scripts/feishu-reply.sh <feishu_chat_id> <feishu_message_id> --stdin
  ```

- Use the IDs from that exact message. Do not reuse IDs from another message.
- Send multiline bodies through explicit `--stdin`; do not put them in a
  positional argument.
- Before calling `scripts/feishu-reply.sh`, verify the reply targets **that**
  exact message (same chat, same thread/quoted parent, same sender, same
  topic). Use the injected thread/recent-chat excerpt, quoted parent, and
  `feishu_mentions` mapping (`<at user_id="open_id">Name</at>`) to resolve
  short follow-ups ("how is it going?", "is it done?") instead of assuming they
  refer to your last unrelated task. If still ambiguous, ask which item they
  mean.
- Never use `cryo-agent send` or `cryo-agent reply` (or any generic local
  outbox/status command) as a Feishu reply.
- If the installed Cryochamber supports `external-ack`
  (`CRYO_EXTERNAL_REPLY_SOURCE=feishu`) and `hibernate` temporarily waits on a
  pending delivery acknowledgement, wait for the connector to finish delivering
  and acknowledging, then retry `hibernate`—do not use `cryo-agent send` as a
  workaround.

## Operator status routing

- External Feishu replies and operator progress notes are separate channels.
- Progress, wake-up notes, and ambient summaries must not be posted into the
  source group/thread unless the user explicitly asked for a group update.
- Send operator-only status with:

  ```bash
  printf '%s\n' "$status" \
    | scripts/proactive-post.sh --user <operator_open_id> --stdin
  ```

- On an ambient wake with no source message, remain silent unless an actionable
  operator alert exists. Never post an ambient summary into a source chat.

## Heavy-task async offload

- Keep the primary Cryochamber session (often running on a fast, low-cost
  triage model) responsive for inbox triage, Feishu replies, scheduling, and
  timely hibernation.
- Do not brute-force heavy, multi-step, or >20-minute work inside the triage
  session. Offload it to one dedicated named `tmux` worker running a stronger
  model that writes a structured deliverable (`work/<task-id>/RESULT.md`) and a
  log file (`work/<task-id>/worker.log`).
- Record the `tmux` session name, task prompt path, `RESULT.md` path, log path,
  and hard deadline in your checkpoint and continuation TODO.
- On follow-up wakes, independently verify the worker's exit status,
  `RESULT.md`, and gates before replying to users; close the `tmux` session
  once the job reaches a terminal state.

## Session lifecycle

- Claim inbox messages and satisfy **Fast first reply** before background work.
- Read the plan, latest checkpoint, and durable notes.
- Update TODOs as work progresses; leave one valid next scheduled TODO unless
  the chamber is intentionally complete.
- At 20 minutes, checkpoint and leave one bounded continuation TODO.
- Hibernate as the final action of a session.

## Safety

- Never publish secrets, raw access keys, private URLs, local-only paths, or
  full prompt transcripts without redaction.
- When in doubt, publish the reusable rule or shape, not the private content.
- Public Cryochamber v0.2.6 has no `external-ack`; feature-detect it.
- Do not claim inbound polling or bot-created/own-thread routing; neither is
  implemented by this starter.
