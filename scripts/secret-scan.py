#!/usr/bin/env python3
"""Deterministic repository-local high-confidence secret scan."""
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}
PATTERNS = {
    "private-key": re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai-key": re.compile(r"\bsk-" + r"[A-Za-z0-9_-]{20,}\b"),
    "aws-access-key": re.compile(r"\bAK" + r"IA[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh" + r"[pousr]_[A-Za-z0-9]{30,}\b"),
    "slack-token": re.compile(r"\bxox" + r"[baprs]-[A-Za-z0-9-]{20,}\b"),
    "bearer-token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}"),
    "assigned-secret": re.compile(
        r"(?i)\b(?:token|secret|password|access[_-]?key)\s*[:=]\s*[\"']?"
        r"[A-Za-z0-9._~+/=-]{24,}"
    ),
    "local-home-path": re.compile(r"/" + r"home/[A-Za-z0-9._-]+/"),
}


def files():
    for directory, names, filenames in os.walk(ROOT):
        names[:] = sorted(name for name in names if name not in SKIP_DIRS)
        for name in sorted(filenames):
            path = Path(directory) / name
            if path.is_symlink() or path == Path(__file__).resolve():
                continue
            yield path


def main():
    hits = []
    for path in files():
        data = path.read_bytes()
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS.items():
                if pattern.search(line):
                    hits.append((str(path.relative_to(ROOT)), number, label))
    for path, number, label in hits:
        print(f"{path}:{number}: {label}")
    print(f"secret-scan: files={sum(1 for _ in files())} hits={len(hits)}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
