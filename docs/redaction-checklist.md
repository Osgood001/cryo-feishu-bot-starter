# Redaction Checklist

Use this before publishing prompts, configs, traces, or wrapper scripts.

## Remove or replace

- Access keys, tokens, passwords, cookies, session IDs, OAuth device codes.
- Raw Feishu `open_id`, `union_id`, `chat_id`, `message_id`, and tenant IDs
  unless they are intentionally public examples.
- Internal hostnames, private IPs, SSH aliases, and local absolute paths.
- Customer data, private documents, message transcripts, and attachments.
- Proprietary benchmark artifacts that are not cleared for sharing.
- Full system/developer prompts if they include private policy, credentials, or
  operational history.

## Keep

- The reusable routing invariant.
- Placeholder-based command templates.
- Minimal examples with fake IDs.
- High-level architecture and session lifecycle.
- Security boundaries and failure modes.

## Suggested placeholders

```text
oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
om_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
cli_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
https://example.internal.invalid
/path/to/project
```

## Final check

Run these before publishing:

```bash
rg -n "accessKey|Authorization|Bearer|token|secret|password|AK|SK|open_id|chat_id|message_id|ou_|oc_|om_|cli_" .
git diff --cached
```

Review matches manually. Some placeholder matches are expected.
