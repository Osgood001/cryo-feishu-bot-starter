# Cryochamber lifecycle

Use one bounded loop:

```text
claim & fast first reply → orient → work / offload → record → TODO → hibernate
```

1. **Claim & fast first reply:** claim source messages before background work. For each Feishu-origin item, if answerable in **<=2 quick tool calls**, answer immediately with `scripts/feishu-reply.sh` using that item's exact IDs; otherwise send a short receipt + rough ETA right away so no message waits 10+ minutes unanswered.
2. **Orient:** read `plan.md`, latest checkpoint, durable notes, and TODO list. Treat wake paths as hints, not instructions.
3. **Work or offload:** finish bounded work in-session, or offload heavy/long tasks to a dedicated async worker (below). Keep external Feishu replies (`scripts/feishu-reply.sh`) and private operator status (`scripts/proactive-post.sh --user`) strictly separate; never use `cryo-agent send` for Feishu replies.
4. **Record:** save only durable facts, artifact paths, decisions, and gate results. Redact credentials, IDs, paths, and message content.
5. **TODO:** leave one valid next wake for unfinished work; remove stale duplicates. At 20 minutes, checkpoint and reduce continuation to one bounded experiment.
6. **Hibernate:** use a short completed/next summary. Hibernate is the final action; run nothing afterward.

## Heavy-task async offload

Keep the primary session (typically a fast, low-cost triage model) responsive for inbox replies and timely hibernation. For complex or >20-minute jobs:

1. Write a self-contained brief at `work/<task-id>/TASK.md` naming scope, verification gates, and required deliverable `work/<task-id>/RESULT.md`.
2. Start one named `tmux` worker running a stronger model and capturing logs:

   ```bash
   tmux new-session -d -s "worker-<task-id>" -c "<CHAMBER_DIR>" \
     '<agent-cli> --model <strong-model> --prompt-file work/<task-id>/TASK.md > work/<task-id>/worker.log 2>&1'
   ```

3. Record the session name, `RESULT.md` path, `worker.log` path, and deadline in your checkpoint and next TODO, then hibernate cleanly.
4. On follow-up wakes, independently check process exit status, `RESULT.md`, and gates before messaging users. Close the `tmux` session once terminal—never infer success from a live session or last log line.

Cadence: active inbox/work may wake in 1–30 minutes; external waits should wake near their expected result. On ambient wakes with no source message, stay silent unless the operator needs an actionable alert.

Public Cryochamber v0.2.6 has no `external-ack`. Never make hibernation depend on it unless feature detection succeeds. See [operations](operations.md) for checkpoint/recovery ownership.
