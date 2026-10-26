# Cryo Feishu Bot Starter

Public-safe reference for a Cryochamber agent that receives Feishu events, replies to the exact source message, records work, schedules its next wake, and hibernates.

## Quickstart

Prerequisites: Linux, Bash, Git, Python 3.10+, Rust/Cargo, Node.js/npm, [Cryochamber v0.2.6](https://github.com/GiggleLiu/cryochamber), and [lark-cli](https://github.com/larksuite/cli). The Feishu app must be published, have bot capability, subscribe to `im.message.receive_v1`, and have the minimum scopes in [Feishu routing](docs/feishu-routing.md).

```bash
cargo install --git https://github.com/GiggleLiu/cryochamber \
  --tag v0.2.6 --locked
npx @larksuite/cli@latest install
cryo --version && cryo-agent --version && lark-cli --version
```

```bash
git clone https://github.com/Osgood001/cryo-feishu-bot-starter.git my-feishu-agent
cd my-feishu-agent
cp .env.example .env
chmod 600 .env
# Replace every REPLACE_WITH_* value; quote values containing spaces.
```

Configure the app without exposing its secret in argv or stdout:

```bash
read -rsp 'Feishu app secret: ' LARK_APP_SECRET; printf '\n'
printf '%s' "$LARK_APP_SECRET" | lark-cli config init \
  --name REPLACE_WITH_LARK_PROFILE_NAME \
  --app-id REPLACE_WITH_FEISHU_APP_ID --app-secret-stdin --brand feishu
unset LARK_APP_SECRET
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME whoami
```

Bot identity comes from the app credentials and bot scopes; it must not run
`auth login`. Only add user OAuth when a deliberate user-only message operation
requires it. Start the least-privilege split flow, then generate a QR image at a
relative path from the returned `verification_url`:

```bash
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME auth login \
  --scope "im:message.send_as_user im:message" --no-wait --json
lark-cli auth qrcode '<verification_url>' --output auth-qr.png
```

Show the URL and QR image to the user. Only after they confirm authorization,
complete the flow in a later step, then remove the QR image. Do not save or log
the `device_code`:

```bash
lark-cli --profile REPLACE_WITH_LARK_PROFILE_NAME auth login \
  --device-code '<device_code>'
rm -f auth-qr.png
```

Install/start the chamber, then run the connector manually or from a supplied supervisor template:

```bash
cryo init --agent codex
set -a; . ./.env; set +a
python3 connector/feishu_connector.py check
cryo start --agent codex
# separate terminal, or systemd/supervisord:
python3 connector/feishu_connector.py run
```

Before using credentials or network, run the deterministic fake-only smoke and full tests:

```bash
scripts/smoke-test.sh
python3 -m unittest discover -s tests -v
python3 scripts/secret-scan.py
```

The smoke queues an exact-ID reply, delivers it only to recording fakes, and proves proactive `DRY_RUN=1` does not invoke even the fake CLI.

## Architecture

```text
Feishu event websocket              exact reply outbox
          │                                 │
          ▼                                 ▼
 lark-cli --as bot ──► connector ──► messages/inbox ──► agent session
                           ▲                                   │
                           └──── ledger / ack / quarantine ◄───┘
operator status: agent ──► proactive-post.sh --user ──► operator DM
```

Public Cryochamber v0.2.6 does **not** provide `external-ack`; the connector probes `cryo-agent external-ack --help` and skips that step when absent. There is no inbound polling fallback and no bot-created/own-thread routing. Thread metadata is preserved only so a reply remains tied to its source message.

```text
.
├── connector/feishu_connector.py    websocket + exact-reply reference
├── scripts/                         reply/status wrappers, smoke, scans
├── templates/                       systemd, supervisord, cron, SSH
├── tests/                            hermetic fakes and contracts
├── docs/                             deployment and operating details
└── messages/{inbox,outbox}/          local handoff directories
```

## Session contract

```text
orient → work → record → TODO → hibernate
```

Reply to each Feishu item with its own `feishu_chat_id` + `feishu_message_id`. Route progress and wake notes to the operator DM. With no user message, remain silent unless an operator alert is actionable. At 20 minutes, checkpoint, leave one bounded continuation TODO, then hibernate.

## Detailed guides

- [Setup and service templates](docs/setup-guide.md)
- [Feishu app, identities, scopes, and routing](docs/feishu-routing.md)
- [Token migration, rotation, backup, and restore](docs/credentials.md)
- [SSH migration](docs/ssh-migration.md)
- [Bounded operations, recovery, upgrade, and rollback](docs/operations.md)
- [Capability matrix and security checklist](docs/security.md)
- [Lifecycle runbook](docs/cryochamber-runbook.md)

License: MIT.
