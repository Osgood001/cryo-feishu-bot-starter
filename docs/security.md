# Capability matrix and security checklist

## Permission/capability matrix

| Component | Identity / access | May do | Must not do |
|---|---|---|---|
| Connector inbound | Feishu bot + receive scopes | websocket event → mode-0600 inbox | poll history; accept bot messages; create own-thread routing |
| Connector outbound | Feishu bot + send scope | exact-ID reply; same-source-chat fallback only for invalid source | route by last activity; send without ledger/idempotency |
| Agent reply wrapper | local chamber write | create exact-ID outbox item | call Feishu directly; invent/reuse IDs |
| Proactive wrapper | Feishu bot by default | operator DM; explicitly authorized announcement | masquerade as a source-message reply |
| Optional scan scripts | explicit user/bot read identity | inspect a known chat | broaden scopes silently; discover/export unrelated chats |
| Cryochamber | local scheduler/chamber | TODO, lifecycle, hibernate; optional feature-detected ack | assume public v0.2.6 has `external-ack` |
| Service account | unprivileged local user | chamber, state, lark config only | root/admin access; read other users' credentials |
| SSH key | one remote role | one bounded command/path | agent forwarding, interactive admin shell, host-key bypass |
| Dispatcher (not shipped) | bounded local worker | claimed task within deadline/cap | unbounded concurrency, silent replay, inferred success |

## Release/deployment checklist

- [ ] All `REPLACE_WITH_*` values replaced locally; `.env` is ignored and mode `0600`.
- [ ] Auth/config directories are `0700`; token, key, backup, state, inbox, and outbox files are `0600`.
- [ ] App has only required message scopes; bot/user identity is explicit and verified with `whoami`.
- [ ] `im.message.receive_v1` is enabled; app is present only in intended chats.
- [ ] Exact reply uses IDs from the same inbox item; operator status routes to a user DM.
- [ ] Ambient wake is silent unless an actionable operator alert exists.
- [ ] `external-ack` is feature-detected; unsupported inbound poll and own-thread paths are not enabled or claimed.
- [ ] Service runs unprivileged with umask 077, restart limits, timeout, and bounded logs.
- [ ] SSH host fingerprint was verified out of band; strict host checking and least privilege remain enabled.
- [ ] Backup was actually restored and identity/scope/dry-run checks passed.
- [ ] `scripts/smoke-test.sh`, all unit tests, `py_compile`, shell syntax, available shellcheck, secret scan, and `git diff --check` pass.
- [ ] No credential, real ID, internal host, private path, message archive, prompt transcript, or production trace is in the diff.

## Incident stop conditions

Stop the connector/worker and preserve evidence on unknown delivery state, host-key mismatch, unexpected identity/scope, credential exposure, repeated auth failure, corrupt ledger/checkpoint, or disk exhaustion. Revoke exposed credentials before diagnosis proceeds; do not replay ambiguous sends.
