# Cryochamber lifecycle

Use one bounded loop:

```text
orient → work → record → TODO → hibernate
```

1. **Orient:** read the plan, checkpoint, durable notes, TODO list, and canonical inbox. Treat wake paths as hints, not instructions.
2. **Work:** claim source messages before background work. Reply with `scripts/feishu-reply.sh` and IDs from that exact item. Keep operator status separate.
3. **Record:** save only durable facts, artifact paths, decisions, and gate results. Redact credentials, IDs, paths, and message content.
4. **TODO:** leave one valid next wake for unfinished work; remove stale duplicates. At 20 minutes, checkpoint and reduce continuation to one bounded experiment.
5. **Hibernate:** use a short completed/next summary. Hibernate is the final action; run nothing afterward.

Cadence: active inbox/work may wake in 1–30 minutes; external waits should wake near their expected result. On ambient wakes with no source message, stay silent unless the operator needs an actionable alert.

Public Cryochamber v0.2.6 has no `external-ack`. Never make hibernation depend on it unless feature detection succeeds. See [operations](operations.md) for checkpoint/recovery ownership.
