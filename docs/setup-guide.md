# Setup and service guide

Start with the [one-page quickstart](../README.md), then complete these checks before a live canary.

## 1. Feishu and lark-cli

- Publish a bot-enabled Feishu app and subscribe to `im.message.receive_v1`.
- Apply only the scopes in [Feishu routing](feishu-routing.md).
- Initialize a named lark-cli profile with `--app-secret-stdin`. Bot identity
  uses app configuration/scopes and must not run `auth login`; when user OAuth
  is required, use the README's scoped `--no-wait --json` → QR → later
  `--device-code` flow.
- Set the profile name, executable paths, bot name/open ID, and local directories in `.env`; never put tokens/app secrets there.
- Confirm `whoami`, `auth scopes`, and `event schema im.message.receive_v1` under the selected profile.

## 2. Local layout and permissions

```bash
mkdir -p messages/inbox messages/outbox .connector
chmod 700 messages messages/inbox messages/outbox .connector
chmod 600 .env
```

Set the lark-cli auth/config directory to `0700` and every credential/backup file to `0600`. The connector creates state/inbox files with restrictive modes but the service account and parent directories remain the operator's responsibility.

## 3. Validate without sending

```bash
scripts/smoke-test.sh
python3 -m unittest discover -s tests -v
python3 -m py_compile connector/feishu_connector.py scripts/*.py tests/*.py tests/fakes/*
for file in scripts/*.sh templates/ssh/*.sh; do bash -n "$file"; done
python3 scripts/secret-scan.py
git diff --check
```

If `shellcheck` is installed, run `shellcheck scripts/*.sh templates/ssh/*.sh`. The fake-only smoke must pass before a CLI dry-run or canary.

## 4. Inspect resolved connector configuration

```bash
set -a; . ./.env; set +a
python3 connector/feishu_connector.py check
```

This probes optional `external-ack` and prints only non-secret configuration. On public Cryochamber v0.2.6, `external_ack` should be false.

## 5. Install one connector supervisor

Choose systemd **or** supervisord, not both.

### systemd user service

Replace every token in `templates/systemd/feishu-connector.service`, copy it to the user's systemd directory, then:

```bash
systemd-analyze verify REPLACE_WITH_RENDERED_SERVICE_PATH
systemctl --user daemon-reload
systemctl --user enable --now feishu-connector.service
systemctl --user status feishu-connector.service
```

### supervisord

Replace every token in `templates/supervisord/feishu-connector.conf`, place it in the configured include directory, then use the supervisor's normal reread/update/status workflow. Ensure its process environment has the same connector values as `.env`; do not embed app secrets or tokens.

The active-node crontab template is for a later bounded job, not for supervising this always-on connector. This repo intentionally does not ship a dispatcher/watchdog implementation; see [operations](operations.md).

## 6. Controlled canary

Use a dedicated test chat and operator account:

1. Send one direct message or group @mention to the bot.
2. Confirm one mode-0600 inbox file with the source IDs.
3. Confirm the agent creates one exact-ID outbox item.
4. Confirm one Feishu reply, then an archived item and terminal ledger state.
5. Confirm an ambient wake produces no source-chat message.

Do not test proactive routing against a production group. Stop on duplicate/unknown delivery, wrong identity, unexpected scopes, or unredacted logs.

## 7. Upgrade/rollback and recovery

Follow [operations](operations.md). Preserve ledger, outbox, quarantine, and checkpoints across code rollback; never delete or blindly replay ambiguous sends. Rotate/revoke/restore credentials with [credentials](credentials.md), and migrate remote access with [SSH migration](ssh-migration.md).
