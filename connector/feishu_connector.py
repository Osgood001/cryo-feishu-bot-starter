#!/usr/bin/env python3
"""Reference Feishu/Lark <-> Cryochamber connector (standard library only).

Inbound : `lark-cli event consume im.message.receive_v1 --as bot` (one JSON event per line)
          -> handled messages become messages/inbox/*.md with exact-ID frontmatter.
Outbound: messages/outbox/*.md written by scripts/feishu-reply.sh
          -> reply to that exact source message (idempotency key), record the delivery in a
             ledger, then `cryo-agent external-ack` (if the installed Cryochamber supports it),
             then archive. Replies stuck longer than DEADLETTER_AFTER_SEC are dead-lettered:
             quarantined, acknowledged, and reported back to the agent as a local notice.

This is a reference: small enough to read in one sitting. It deliberately has no
"reply to the last active chat" fallback -- every reply needs the IDs of its own source.

Usage:
  feishu_connector.py run        # both loops, long-running (systemd/supervisord)
  feishu_connector.py outbound   # outbox loop only
  feishu_connector.py once       # process the outbox once and exit (smoke tests)
  feishu_connector.py check      # print resolved, non-secret configuration
Configuration is environment-only; see .env.example.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

ENV = os.environ
CHAMBER = os.path.abspath(ENV.get("CHAMBER_DIR", "."))
INBOX = os.path.join(CHAMBER, "messages", "inbox")
OUTBOX = os.path.join(CHAMBER, "messages", "outbox")
ARCHIVE = os.path.join(OUTBOX, "archive")
QUARANTINE = os.path.join(OUTBOX, "quarantine")
STATE = os.path.abspath(ENV.get("CONNECTOR_STATE_DIR", os.path.join(CHAMBER, ".connector")))
LEDGER = os.path.join(STATE, "ledger")
SEEN = os.path.join(STATE, "seen")
LARK = ENV.get("LARK_CLI", "lark-cli")
PROFILE = ENV.get("LARK_CLI_PROFILE", "")
CRYO_AGENT = ENV.get("CRYO_AGENT", "cryo-agent")
BOT_NAME = ENV.get("FEISHU_BOT_NAME", "")
BOT_OPEN_ID = ENV.get("FEISHU_BOT_OPEN_ID", "")
SIGNATURE = ENV.get("BOT_SIGNATURE", "")
POLL_SEC = float(ENV.get("OUTBOX_POLL_SEC", "2"))
DEADLETTER_AFTER_SEC = int(ENV.get("DEADLETTER_AFTER_SEC", "900"))
MAX_REPLY_CHARS = int(ENV.get("MAX_REPLY_CHARS", "20000"))
SOURCE = "feishu"

CHAT_RE = re.compile(r"^oc_[A-Za-z0-9]+$")
MSG_RE = re.compile(r"^om_[A-Za-z0-9]+$")
# Feishu "the source message no longer exists" -> safe to post top-level in the same chat.
INVALID_SOURCE_CODES = {99992354}
SKIP_TYPES = {"system", "share_calendar_event", "calendar", "red_packet"}

_ID_RE = re.compile(r"\b(ou|oc|om|on|cli)_[A-Za-z0-9]{4,}")
_SECRET_RE = re.compile(r"(?i)(bearer\s+|token[\"'=: ]+|secret[\"'=: ]+)[A-Za-z0-9._\-]{8,}")


def redact(text):
    """Logs keep the ID kind and 4 chars, never full IDs or token-looking values."""
    text = _ID_RE.sub(lambda m: m.group(0)[: len(m.group(1)) + 5] + "…", str(text))
    return _SECRET_RE.sub(lambda m: m.group(1) + "<redacted>", text)


def log(*parts):
    line = " ".join(str(p) for p in parts)
    sys.stderr.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + redact(line) + "\n")
    sys.stderr.flush()


def _lark(*args):
    cmd = [LARK]
    if PROFILE:
        cmd += ["--profile", PROFILE]
    return cmd + list(args)


def _atomic_write(path, data, mode=0o600):
    tmp = path + ".tmp-%d" % os.getpid()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    # Persist the rename as well as the file contents before recording later state.
    directory = os.open(os.path.dirname(path) or ".", os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _ensure_dirs():
    for d in (INBOX, OUTBOX, ARCHIVE, QUARANTINE):
        os.makedirs(d, exist_ok=True)
    for d in (STATE, LEDGER, SEEN):
        os.makedirs(d, mode=0o700, exist_ok=True)


# ---------------------------------------------------------------- inbound
def _claim(message_id):
    """Reserve a message; an interrupted pending reservation remains retryable."""
    key = hashlib.sha256(message_id.encode()).hexdigest()
    path = os.path.join(SEEN, key)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("pending\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True
    except FileExistsError:
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read().strip() == "pending"
        except OSError:
            return False


def _mark_seen(message_id):
    key = hashlib.sha256(message_id.encode()).hexdigest()
    _atomic_write(os.path.join(SEEN, key), "seen\n", mode=0o600)


def _text_of(content):
    """lark-cli pre-renders most message types to readable text; tolerate raw JSON too."""
    if isinstance(content, dict):
        return str(content.get("text", ""))
    text = str(content or "")
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and isinstance(data.get("text"), str):
                return data["text"]
        except ValueError:
            pass
    return text


def should_handle(ev, text):
    """Direct messages always; group messages only when they mention the bot."""
    if ev.get("chat_type") == "p2p":
        return True
    mentions = ev.get("mentions") or []
    if BOT_OPEN_ID and any(isinstance(m, dict) and m.get("id") == BOT_OPEN_ID for m in mentions):
        return True
    return bool(BOT_NAME) and ("@" + BOT_NAME).lower() in text.lower()


def write_inbox(ev):
    mid, chat = ev.get("message_id") or "", ev.get("chat_id") or ""
    if not (MSG_RE.match(mid) and CHAT_RE.match(chat)):
        return None
    if ev.get("sender_type", "user") != "user":  # never react to bots, including ourselves
        return None
    if ev.get("message_type") in SKIP_TYPES:
        return None
    text = _text_of(ev.get("content")).strip()
    if not text or not should_handle(ev, text) or not _claim(mid):
        return None
    stamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    path = os.path.join(INBOX, "%s_%s.md" % (stamp, hashlib.sha256(mid.encode()).hexdigest()[:12]))
    front = [
        "---",
        "from: feishu",
        "source: feishu",
        "feishu_chat_id: " + chat,
        "feishu_message_id: " + mid,
        "feishu_chat_type: " + (ev.get("chat_type") or "unknown"),
        "feishu_sender: " + (ev.get("sender_id") or "unknown"),
        "feishu_thread_id: " + (ev.get("thread_id") or ""),
        "---",
        "",
        text,
        "",
    ]
    _atomic_write(path, "\n".join(front), mode=0o600)
    _mark_seen(mid)
    log("inbox <-", mid, "chat", chat)
    return path


def consume_loop():
    while True:
        proc = None
        try:
            proc = subprocess.Popen(_lark("event", "consume", "im.message.receive_v1", "--as", "bot"),
                                    stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True, bufsize=1)
            for line in proc.stdout:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("type", "im.message.receive_v1") == "im.message.receive_v1":
                    write_inbox(ev)
        except OSError as exc:
            log("consumer error:", exc)
        finally:
            if proc and proc.poll() is None:
                proc.terminate()
        log("consumer ended; restarting in 3s")
        time.sleep(3)


# ---------------------------------------------------------------- outbound
def parse_reply(path):
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()
    if not raw.startswith("---\n") or "\n---\n" not in raw[4:]:
        return None, None
    head, body = raw[4:].split("\n---\n", 1)
    front = {}
    for line in head.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            front[key.strip()] = value.strip()
    return front, body.strip("\n")


def _ledger_path(mid, body):
    key = hashlib.sha256((SOURCE + "\0" + mid + "\0" + body).encode()).hexdigest()
    return key, os.path.join(LEDGER, key + ".json")


def _ledger(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _set_state(path, record, state):
    record = dict(record, state=state, updated=int(time.time()))
    _atomic_write(path, json.dumps(record))
    return record


def _send(args):
    """Return 'ok' | 'invalid_source' | 'failed' | 'unknown' for one lark-cli call.

    Success needs exit 0 *and* exactly one JSON envelope with "ok": true (stdout or stderr).
    Anything ambiguous is 'unknown' and retried later; the idempotency key makes retries safe.
    """
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=40, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        log("send error:", exc)
        return "unknown"
    envelopes = []
    for raw in (res.stdout, res.stderr):
        try:
            data = json.loads(raw or "")
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("ok"), bool):
            envelopes.append(data)
    if len(envelopes) != 1:
        log("send result unknown rc=%s" % res.returncode)
        return "unknown"
    data = envelopes[0]
    if res.returncode == 0 and data["ok"]:
        return "ok"
    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    if not data["ok"] and error.get("code") in INVALID_SOURCE_CODES:
        return "invalid_source"
    log("send failed rc=%s code=%s" % (res.returncode, error.get("code")))
    return "failed"


def deliver(chat, mid, body, key):
    text = body + (("\n\n" + SIGNATURE) if SIGNATURE else "")
    idem = key[:40]  # lark-cli idempotency keys are limited to 50 characters
    outcome = _send(_lark("im", "+messages-reply", "--message-id", mid, "--markdown", text,
                          "--as", "bot", "--format", "json", "--idempotency-key", idem))
    if outcome == "invalid_source":
        # The source message is gone; the chat id came from the same message, so a
        # top-level post still reaches the right conversation.
        outcome = _send(_lark("im", "+messages-send", "--chat-id", chat, "--markdown", text,
                              "--as", "bot", "--format", "json", "--idempotency-key", "f" + idem[:39]))
    return outcome == "ok"


_ACK_SUPPORTED = None


def ack_supported():
    """`cryo-agent external-ack` exists only in Cryochamber builds that include it."""
    global _ACK_SUPPORTED
    if _ACK_SUPPORTED is None:
        try:
            res = subprocess.run([CRYO_AGENT, "external-ack", "--help"], capture_output=True,
                                 text=True, timeout=15, stdin=subprocess.DEVNULL)
            _ACK_SUPPORTED = res.returncode == 0
        except (OSError, subprocess.SubprocessError):
            _ACK_SUPPORTED = False
        log("external-ack supported:", _ACK_SUPPORTED)
    return _ACK_SUPPORTED


def external_ack(mid):
    if not ack_supported():
        return True  # nothing to acknowledge on this Cryochamber build
    try:
        res = subprocess.run([CRYO_AGENT, "external-ack", "--source", SOURCE, "--message-id", mid],
                             cwd=CHAMBER, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        log("external-ack error:", exc)
        return False
    out = (res.stdout + res.stderr).strip()
    summary = re.search(r"matched=(\d+),\s*already=(\d+),\s*unknown=(\d+)", out)
    if summary:
        matched, already, unknown = (int(value) for value in summary.groups())
        return unknown == 0 and (matched > 0 or already > 0)
    if res.returncode == 0:
        return True
    # No running session, or the id is not an obligation of the current one: nothing to clear.
    return out.startswith("Error: No active session")


def _move(path, directory):
    os.replace(path, os.path.join(directory, os.path.basename(path)))


def _deadletter(path, front, age):
    _move(path, QUARANTINE)
    mid = front.get("feishu_message_id", "")
    if MSG_RE.match(mid):
        external_ack(mid)
    notice = os.path.join(INBOX, time.strftime("%Y-%m-%dT%H-%M-%S") + "_delivery-failed.md")
    _atomic_write(notice, "---\nfrom: connector\nsource: local\nsubject: delivery failed\n---\n\n"
                  "A reply could not be delivered within %d s and was quarantined as %s. "
                  "Do not resend blindly; check the source message, then reply again with its exact IDs.\n"
                  % (age, os.path.basename(path)))
    log("dead-lettered", os.path.basename(path), "after", age, "s")


def process_outbox_once():
    handled = 0
    for name in sorted(os.listdir(OUTBOX)):
        path = os.path.join(OUTBOX, name)
        if not name.endswith(".md") or name.startswith(".") or not os.path.isfile(path):
            continue
        front, body = parse_reply(path)
        age = int(time.time() - os.path.getmtime(path))
        chat, mid = (front or {}).get("feishu_chat_id", ""), (front or {}).get("feishu_message_id", "")
        if not front or not CHAT_RE.match(chat) or not MSG_RE.match(mid) or not body \
                or len(body) > MAX_REPLY_CHARS:
            log("invalid outbox item quarantined:", name)
            _move(path, QUARANTINE)
            continue
        key, ledger = _ledger_path(mid, body)
        record = _ledger(ledger) or {"chat": chat, "message": mid, "state": "prepared"}
        if record.get("state") == "prepared":
            record = _set_state(ledger, record, "prepared")
            if not deliver(chat, mid, body, key):
                if age >= DEADLETTER_AFTER_SEC:
                    _deadletter(path, front, age)
                continue
            record = _set_state(ledger, record, "delivered")
        if record.get("state") in ("delivered", "ack_pending"):
            record = _set_state(ledger, record, "ack_pending")
            if not external_ack(mid):
                if age < DEADLETTER_AFTER_SEC:
                    continue  # delivered; retry only the acknowledgement next pass
                log("ack gave up after", age, "s; reply was delivered", mid)
            record = _set_state(ledger, record, "acked")
        _move(path, ARCHIVE)
        handled += 1
        log("delivered + acked", mid)
    return handled


def outbox_loop():
    while True:
        try:
            process_outbox_once()
        except OSError as exc:
            log("outbox error:", exc)
        time.sleep(POLL_SEC)


def main(argv):
    mode = argv[1] if len(argv) > 1 else "run"
    _ensure_dirs()
    if mode == "check":
        print(json.dumps({"chamber": CHAMBER, "state": STATE, "lark_cli": LARK, "profile_set": bool(PROFILE),
                          "bot_name_set": bool(BOT_NAME), "bot_open_id_set": bool(BOT_OPEN_ID),
                          "deadletter_after_sec": DEADLETTER_AFTER_SEC, "external_ack": ack_supported()}, indent=1))
        return 0
    if mode == "once":
        print("handled", process_outbox_once())
        return 0
    if mode == "outbound":
        outbox_loop()
    if mode == "run":
        threading.Thread(target=consume_loop, daemon=True).start()
        outbox_loop()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
