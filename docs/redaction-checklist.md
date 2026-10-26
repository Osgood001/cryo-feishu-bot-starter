# Public redaction checklist

Remove credentials, OAuth/device codes, cookies, real Feishu IDs, tenant/app identifiers, internal hosts/IPs, private paths, message content, attachments, prompt transcripts, production traces, and infrastructure names.

Keep only reusable invariants, placeholder examples, high-level diagrams, negative boundaries, and deterministic fake evidence.

Before publishing:

```bash
python3 scripts/secret-scan.py
git diff --check
git diff -- . ':!*.log'
```

The scanner is a high-confidence gate, not proof of absence. Manually inspect every placeholder-like ID, URL, hostname, absolute path, auth command, fixture, and generated artifact. A backup checksum proves integrity, not recoverability; test an actual restore as described in [credentials](credentials.md).
