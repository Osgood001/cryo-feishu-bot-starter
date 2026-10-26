# Bounded operations

## Dispatch contract (implementation deferred)

This repository does **not** ship an `ops/dispatch` runner or watchdog. The active-node crontab file is only a gate/lock/timeout pattern; replace its command with a reviewed bounded runner. A later implementation is acceptable only if tests prove this contract:

1. Queue entries are immutable task directories with task ID, scope, hard deadline, allowed mutations, and required `RESULT.md`.
2. Claim is an atomic move from `queued/` to `active/`; one task has at most one owner.
3. Global concurrency and memory/disk floors are checked before every launch. No new work starts after the deadline or on a non-active node.
4. Each worker has one process/session, a hard timeout, captured exit status, and a durable checkpoint path.
5. Success moves to `done/` only after `RESULT.md` and declared gates pass. Timeout/crash moves to `failed/` or remains recoverable in `active/`; it is never silently rerun.
6. Recovery verifies task identity, checkpoint completeness, terminal state, and content hash before skipping completed work.

## tmux, watchdog, and timeout ownership

Use tmux only when a process must survive the current agent session. Short commands stay in the foreground so their exit status remains visible. Every cross-session tmux job must have an owner, task ID, start/deadline, checkpoint, log path, and cleanup rule.

The launcher owns admission and hard timeout. The worker owns incremental checkpoints and graceful stop. The watchdog owns stale-process detection, evidence capture, termination escalation, and requeue/quarantine policy. The next agent session owns recovery validation. A watchdog must never infer success from a live tmux session or a final log line.

## 20-minute continuation

At or before 20 minutes:

1. Stop starting new work.
2. Record completed artifacts, exact gates, failures, process IDs, and safe resume command.
3. Leave one bounded TODO naming the next experiment and decision rule.
4. Terminate or hand off owned subprocesses; retain tmux only under the contract above.
5. Hibernate as the final action.

## Active-node cron

`templates/crontab.active-node.example` orders checks as marker → nonblocking lock → 15-minute timeout → command. The marker must live on node-local storage and only one node may own it. Log rotation and alerting remain operator responsibilities.

## Upgrade and rollback

1. Pin current Cryochamber, lark-cli, Python, and repository revisions; back up non-secret state and prove restore.
2. Run hermetic tests and fake-only smoke on the candidate. Re-check CLI help/schema and `external-ack` feature detection.
3. Stop one connector, preserve ledger/outbox, deploy to a canary host/chat, and validate one inbound plus exact reply.
4. Promote one node at a time. Never run two consumers for the same profile unless the upstream event contract explicitly supports it.
5. Roll back by stopping the candidate, restoring the pinned code/config, retaining ledger/outbox/quarantine, and re-running checks before start. Do not delete or replay ambiguous delivered items.
