#!/usr/bin/env bash
# Fetch a candidate host key, verify its SHA256 fingerprint out of band, then install it.
set -euo pipefail

host="${1:-}"
expected="${2:-}"
port="${3:-22}"

if [[ -z "$host" || ! "$expected" =~ ^SHA256:[A-Za-z0-9+/=]+$ || ! "$port" =~ ^[0-9]+$ ]]; then
  echo "usage: $0 <hostname> <SHA256:fingerprint-from-trusted-channel> [port]" >&2
  exit 2
fi

umask 077
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
candidate="$(mktemp)"
trap 'rm -f -- "$candidate"' EXIT
ssh-keyscan -p "$port" -H -- "$host" >"$candidate" 2>/dev/null

if ! ssh-keygen -lf "$candidate" -E sha256 | awk '{print $2}' | grep -Fxq -- "$expected"; then
  echo "error: host-key fingerprint mismatch; known_hosts unchanged" >&2
  exit 1
fi

cat "$candidate" >>"$HOME/.ssh/known_hosts"
chmod 600 "$HOME/.ssh/known_hosts"
echo "installed verified host key for $host"
