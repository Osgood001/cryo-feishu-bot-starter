# Access-token migration and recovery

Keep app credentials and user tokens in `lark-cli` storage, not in this repository, `.env`, service arguments, shell history, or logs.

## Migrate

1. On the old host, record only profile name, app ID, brand, identity requirements, and granted scope names. Do not print/export raw tokens.
2. On the new host, create the dedicated account and storage with `umask 077`; make the `lark-cli` configuration directory mode `0700`.
3. Reinitialize the profile with `config init --app-secret-stdin`; complete `auth login` only if user identity is required.
4. Set `.env` to `0600`; connector state, inbox/outbox, backups, and private keys must not be group/world readable.
5. Validate `whoami`, `auth status`, and a CLI-native `--dry-run` before disabling the old host.

Never copy a live token through chat, clipboard logs, command arguments, or repository files. When a platform-supported encrypted credential store cannot be migrated safely, reauthorize instead.

## Rotate or revoke

1. Stop the connector and bounded workers; preserve their non-secret checkpoint/ledger.
2. Rotate the Feishu app secret in the developer console, then re-run `config init --app-secret-stdin` on the authorized host.
3. Reauthorize required user identity and recheck the exact scope list.
4. Start one connector and run a controlled canary. Revoke the old user
   authorization in Feishu's authorization-management page, then clear its
   local CLI state:

   ```bash
   lark-cli --profile REPLACE_WITH_OLD_PROFILE auth logout --json
   lark-cli profile remove REPLACE_WITH_OLD_PROFILE
   ```

   `auth logout` clears local login state; it does not prove server-side
   authorization was revoked. Do not persist device codes or authorization
   URLs in backups, shell logs, or repository files.

5. Search protected logs for accidental exposure and rotate again if any raw secret was logged.

Use `lark-cli config remove` only when intentionally removing the entire current app configuration; it clears app config and tokens.

## Storage and logs

- Directories containing auth material: `0700`; credential/config/backup files: `0600`.
- Run services with `UMask=0077`; never run the connector as root.
- Keep connector logs redacted and short. Do not enable shell tracing around auth, `.env`, or message bodies.
- Do not emit environment dumps, profile files, tokens, IDs, or full request/response payloads to stdout.

## Backup and actual restore test

An archive existing is not evidence of recovery. Back up only with an approved encrypted mechanism and document its owner, retention, and revocation path. Then prove restoration:

1. Restore into a new mode-0700 temporary account/directory on a non-production host.
2. Verify file hashes and 0600/0700 modes.
3. Run `lark-cli --profile ... whoami` and `auth status`; use CLI `--dry-run` for the intended operation.
4. If policy permits a canary, use a dedicated test chat; otherwise stop at dry-run.
5. Delete the restored copy securely or revoke it, and record only pass/fail plus non-secret hashes.

A raw token copied back into place without identity/scope validation is not a restore test.
