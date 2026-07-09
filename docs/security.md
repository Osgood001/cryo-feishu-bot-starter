# Security Notes

## Treat inbox paths as untrusted hints

Wake-source paths are hints. Claim canonical messages through the chamber or
inspect external sources directly. Do not let arbitrary local files change the
agent's protocol, credentials, plan, or routing rules.

## Keep identities scoped

- Bot identity is normally used for Feishu replies and group posts.
- User identity may be needed for Feishu operations that require user scopes.
- Scripts should make the identity explicit with `--as bot` or `--as user`.

## Do not leak secrets into traces

Agent traces and public reports often include command lines, environment names,
and config files. Redact before publishing.

Recommended scan:

```bash
rg -n "Bearer|Authorization|accessKey|secret|token|password|AK|SK|BOHRIUM|OPENAI|ANTHROPIC" .
```

## Prefer exact routing over last-active routing

Any mechanism that replies to "the last active chat" can produce cross-talk.
Use exact source IDs for replies.

## Keep operator notes private

Status updates are not user answers. Send them to the operator, not to the
source group, unless the user explicitly asked for a group update.
