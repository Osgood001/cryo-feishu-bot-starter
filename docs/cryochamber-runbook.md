# Cryochamber Runbook

This is the minimal lifecycle for a long-running scheduled agent.

## 1. Orient

- Read `plan.md` or the equivalent project plan.
- Read durable notes if they exist.
- Run `cryo-agent todo list` or your scheduler's TODO equivalent.
- Inspect the prompt-provided inbox summary.

## 2. Work

- Claim canonical inbox messages before background work.
- For each Feishu-origin message, reply with `scripts/feishu-reply.sh` and the
  exact IDs from that message.
- Use local files and source repos as ground truth when answering code or
  operations questions.
- Update TODOs as work is completed.

## 3. Record

- Record only durable facts that future sessions cannot reconstruct from the
  session summary, code, or outbox.
- Avoid appending noisy session journals to durable notes.
- Keep notes short and editable.

## 4. Confirm next wake

- The next wake should be represented as a pending TODO with a valid time.
- Do not rely on an implicit daemon wake if there is more work to do.
- Remove stale or duplicate TODOs.

## 5. Hibernate

- Hibernate is the last action.
- Do not run commands after hibernating.
- Use a short summary that says what happened and what is next.

## Default cadence

- Inbox or active work: wake again in 1-30 minutes.
- Waiting on an external event: wake near the expected completion time.
- Quiet periods: keep a conservative heartbeat if the project requires proactive
  monitoring.
