# SSH migration

Use SSH only for a bounded remote command or controlled file transfer. Do not make remote login a credential-distribution mechanism.

## Safe workflow

1. Generate a dedicated key for one role; protect the private key and `.ssh` directory with `0600`/`0700`.
2. Copy `templates/ssh/config.example`, replace the alias/host/user/key placeholders, and keep `StrictHostKeyChecking yes` plus `IdentitiesOnly yes`.
3. Obtain the host-key SHA256 fingerprint from an authenticated, independent channel. Install it with:

   ```bash
   templates/ssh/known-hosts-setup.sh host.example.invalid \
     SHA256:REPLACE_WITH_VERIFIED_FINGERPRINT 22
   ```

   `ssh-keyscan` alone is not authentication; the script changes `known_hosts` only when a fetched key matches the supplied fingerprint.
4. Test a non-login command:

   ```bash
   ssh REPLACE_WITH_HOST_ALIAS -- /usr/bin/id
   ```

5. Restrict the remote key in `authorized_keys` with the narrowest viable forced command/source/network options. Use a dedicated unprivileged remote account.

## Boundaries

- Prefer `ssh alias -- command`; do not depend on interactive/login-shell startup files.
- Use absolute remote executable paths and a minimal remote `PATH`.
- Never pass secrets in argv, echo them, print `env`, enable `set -x`, or copy them into a repository.
- Never use `StrictHostKeyChecking=no`, accept a changed key automatically, forward an agent by default, or reuse a personal/admin key.
- Migrate one host at a time; keep the old path disabled but recoverable until the new alias, host key, least privilege, and bounded command have been verified.

Rollback means disable the new key/alias, restore the previously verified host-key entry and command path, and revalidate before re-enabling work. A host-key mismatch is a stop condition, not a retry hint.
