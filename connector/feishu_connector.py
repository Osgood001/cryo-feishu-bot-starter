#!/usr/bin/env python3
"""Reference Feishu/Lark <-> Cryochamber connector (standard library only).

Inbound : `lark-cli event consume im.message.receive_v1 --as bot` (one JSON event per line)
          -> handled messages become messages/inbox/*.md with exact-ID frontmatter,
             @ mention mapping, exact reply command hint, and optional thread/chat context.
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
CONTEXT_MESSAGES = max(0, min(50, int(ENV.get("FEISHU_CONTEXT_MESSAGES", "0"))))
CONTEXT_ITEM_CHARS = 300
QUOTED_MAX_CHARS = 500
SOURCE = "feishu"

CHAT_RE = re.compile(r"^oc_[A-Za-z0-9]+$")
MSG_RE = re.compile(r"^om_[A-Za-z0-9]+$")
THREAD_RE = re.compile(r"^omt_[A-Za-z0-9]+$")
OPEN_ID_RE = re.compile(r"^ou_[A-Za-z0-9]+$")
# Feishu "the source message no longer exists" -> safe to post top-level in the same chat.
INVALID_SOURCE_CODES = {99992354}
SKIP_TYPES = {"system", "share_calendar_event", "calendar", "red_packet"}

_ID_RE = re.compile(r"\b(ou|oc|om|omt|on|cli)_[A-Za-z0-9]{4,}")
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


def _lark_json(*args, timeout=20):
    """Run lark-cli and parse one JSON object; return None on any error."""
    try:
        res = subprocess.run(_lark(*args), capture_output=True, text=True,
                             timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        log("lark-cli context fetch failed:", exc)
        return None
    if res.returncode != 0:
        return None
    try:
        data = json.loads(res.stdout or "{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


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


def _flatten_post(data):
    """Flatten a Feishu rich-text `post` payload to plain text."""
    if not isinstance(data, dict):
        return ""
    if "content" not in data:
        for value in data.values():
            if isinstance(value, dict) and "content" in value:
                data = value
                break
    rows = data.get("content")
    if not isinstance(rows, list):
        return ""
    lines = []
    for row in rows:
        if not isinstance(row, list):
            continue
        parts = []
        for seg in row:
            if not isinstance(seg, dict):
                continue
            if seg.get("tag") == "at":
                name = str(seg.get("user_name") or "").strip()
                parts.append("@" + name if name else "@")
            else:
                parts.append(str(seg.get("text") or ""))
        lines.append("".join(parts))
    title = str(data.get("title") or "").strip()
    body = "\n".join(lines).strip()
    return (title + "\n" + body).strip() if title else body


def _text_of(content):
    """lark-cli pre-renders most message types to readable text; tolerate raw JSON too."""
    if isinstance(content, dict):
        if "text" in content and "content" not in content:
            return str(content.get("text", ""))
        return _flatten_post(content) or json.dumps(content, ensure_ascii=False)
    text = str(content or "")
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if isinstance(data.get("text"), str) and "content" not in data:
                    return data["text"]
                flat = _flatten_post(data)
                if flat:
                    return flat
        except ValueError:
            pass
    return text


def _mention_open_id(mention):
    """Extract an open_id string from flat or nested Feishu mention dicts."""
    if not isinstance(mention, dict):
        return ""
    raw_id = mention.get("id")
    if isinstance(raw_id, dict):
        raw_id = raw_id.get("open_id") or raw_id.get("user_id") or ""
    return str(raw_id or "").strip()


def _extract_mentions(ev):
    """Return deduplicated [(display_name, open_id)] for non-bot @mentions."""
    seen, out = set(), []
    for item in (ev.get("mentions") or []):
        open_id = _mention_open_id(item)
        if not OPEN_ID_RE.match(open_id) or open_id == BOT_OPEN_ID or open_id in seen:
            continue
        seen.add(open_id)
        name = str(item.get("name") or "").strip() or open_id
        out.append((name, open_id))
    return out


def _resolve_mentions_in_text(text, mentions):
    """Replace placeholder mention keys (e.g. @_user_1) with @DisplayName."""
    for item in (mentions or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        name = str(item.get("name") or "").strip()
        if key and name and key in text:
            text = text.replace(key, "@" + name)
    return text


def _compact_excerpt(text, limit):
    return " ".join(str(text or "").split())[:limit]


def _sender_label(msg):
    """Human-readable label for a context message sender."""
    sender = msg.get("sender") if isinstance(msg.get("sender"), dict) else {}
    sid = str(sender.get("id") or msg.get("sender_id") or "").strip()
    if BOT_OPEN_ID and sid == BOT_OPEN_ID:
        return "bot"
    if str(sender.get("sender_type") or msg.get("sender_type") or "").strip() == "app":
        return "bot"
    name = str(msg.get("sender_name") or sender.get("name") or "").strip()
    if name:
        return name
    return "user"


def _fetch_quoted(parent_id):
    if not MSG_RE.match(parent_id or ""):
        return None
    data = _lark_json("im", "+messages-mget", "--message-ids", parent_id,
                      "--as", "bot", "--format", "json")
    if not data:
        return None
    payload = data.get("data") or {}
    items = payload.get("messages") or payload.get("items") or []
    if not items or not isinstance(items[0], dict):
        return None
    parent = items[0]
    raw_content = parent.get("content")
    if raw_content is None and isinstance(parent.get("body"), dict):
        raw_content = parent["body"].get("content")
    text = _compact_excerpt(_text_of(raw_content), QUOTED_MAX_CHARS)
    if not text:
        return None
    return (_sender_label(parent), text)


def _extract_context_items(messages, current_mid, reverse=False):
    items = list(reversed(messages)) if reverse else list(messages)
    out = []
    for msg in items:
        if not isinstance(msg, dict):
            continue
        if str(msg.get("message_id") or "") == current_mid:
            continue
        raw_content = msg.get("content")
        if raw_content is None and isinstance(msg.get("body"), dict):
            raw_content = msg["body"].get("content")
        text = _compact_excerpt(_text_of(raw_content), CONTEXT_ITEM_CHARS)
        if not text:
            continue
        out.append((_sender_label(msg), text))
    return out


def _fetch_thread_context(thread_id, current_mid, limit):
    if not THREAD_RE.match(thread_id or "") or limit <= 0:
        return []
    data = _lark_json("im", "+threads-messages-list", "--thread", thread_id,
                      "--as", "bot", "--order", "asc", "--no-reactions",
                      "--page-size", str(limit), "--format", "json")
    if not data:
        return []
    payload = data.get("data") or {}
    msgs = payload.get("messages") or payload.get("items") or []
    return _extract_context_items(msgs, current_mid, reverse=False)


def _fetch_recent_chat(chat_id, current_mid, limit):
    if not CHAT_RE.match(chat_id or "") or limit <= 0:
        return []
    data = _lark_json("im", "+chat-messages-list", "--chat-id", chat_id,
                      "--as", "bot", "--order", "desc", "--no-reactions",
                      "--page-size", str(limit), "--format", "json")
    if not data:
        return []
    payload = data.get("data") or {}
    msgs = payload.get("messages") or payload.get("items") or []
    return _extract_context_items(msgs, current_mid, reverse=True)


def _conversation_context(ev, chat, mid):
    """Return (kind, [(sender, excerpt), ...], quoted_or_none).

    Uses pre-supplied event context when present; otherwise fetches via lark-cli
    only when FEISHU_CONTEXT_MESSAGES > 0 (opt-in, best-effort).
    """
    chat_type = str(ev.get("chat_type") or "")
    thread_id = str(ev.get("thread_id") or "")
    reply_to = str(ev.get("reply_to") or ev.get("parent_id") or "")

    quoted = None
    inline_quoted = ev.get("quoted_message")
    if isinstance(inline_quoted, dict):
        qtext = _compact_excerpt(_text_of(inline_quoted.get("text") or inline_quoted.get("content")),
                                 QUOTED_MAX_CHARS)
        if qtext:
            quoted = (str(inline_quoted.get("sender") or "user"), qtext)
    elif CONTEXT_MESSAGES > 0 and MSG_RE.match(reply_to):
        quoted = _fetch_quoted(reply_to)

    inline_ctx = ev.get("context_messages")
    if isinstance(inline_ctx, list) and inline_ctx:
        kind = "thread" if (chat_type != "p2p" and THREAD_RE.match(thread_id)) else "chat"
        entries = []
        for item in inline_ctx[-max(CONTEXT_MESSAGES, 20):]:
            if isinstance(item, dict):
                txt = _compact_excerpt(_text_of(item.get("text") or item.get("content")), CONTEXT_ITEM_CHARS)
                if txt:
                    entries.append((str(item.get("sender") or "user"), txt))
        if entries:
            return kind, entries, quoted

    if CONTEXT_MESSAGES <= 0:
        return "", [], quoted

    if chat_type != "p2p" and THREAD_RE.match(thread_id):
        entries = _fetch_thread_context(thread_id, mid, CONTEXT_MESSAGES)
        if entries:
            return "thread", entries, quoted
    entries = _fetch_recent_chat(chat, mid, CONTEXT_MESSAGES)
    if entries:
        return "chat", entries, quoted
    return "", [], quoted


def should_handle(ev, text):
    """Direct messages always; group messages only when they mention the bot."""
    if ev.get("chat_type") == "p2p":
        return True
    mentions = ev.get("mentions") or []
    if BOT_OPEN_ID and any(_mention_open_id(m) == BOT_OPEN_ID for m in mentions):
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
    raw_mentions = ev.get("mentions") or []
    text = _resolve_mentions_in_text(_text_of(ev.get("content")).strip(), raw_mentions)
    if not text or not should_handle(ev, text) or not _claim(mid):
        return None
    sender_name = str(ev.get("sender_name") or "").strip()
    reply_to = str(ev.get("reply_to") or ev.get("parent_id") or "").strip()
    thread_id = str(ev.get("thread_id") or "").strip()
    mention_pairs = _extract_mentions(ev)
    convo_kind, convo_msgs, quoted = _conversation_context(ev, chat, mid)
    stamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    path = os.path.join(INBOX, "%s_%s.md" % (stamp, hashlib.sha256(mid.encode()).hexdigest()[:12]))
    lines = [
        "---",
        "from: feishu",
        "source: feishu",
        "feishu_chat_id: " + chat,
        "feishu_message_id: " + mid,
        "feishu_chat_type: " + (ev.get("chat_type") or "unknown"),
        "feishu_sender: " + (ev.get("sender_id") or "unknown"),
        "feishu_sender_name: " + sender_name,
        "feishu_mentions: " + "; ".join("%s=%s" % (name, oid) for name, oid in mention_pairs),
        "feishu_reply_to: " + reply_to,
        "feishu_thread_id: " + thread_id,
        "---",
        "",
        text,
        "",
        "---",
    ]
    if sender_name:
        lines.append("System note: sender display name: " + sender_name)
    if convo_msgs:
        label = "thread" if convo_kind == "thread" else "recent chat"
        lines.append("System note: %s context (chronological; use for follow-ups):" % label)
        for who, excerpt in convo_msgs:
            lines.append("> [%s] %s" % (who, excerpt))
    if quoted:
        qwho, qtext = quoted
        lines.append("System note: quoted parent message (target of 'this/that/above'):")
        lines.append("> [%s] %s" % (qwho, qtext))
    if mention_pairs:
        mapping = "; ".join("%s=%s" % (name, oid) for name, oid in mention_pairs)
        lines.append(
            'System note: mentioned users (use <at user_id="open_id">Name</at> to mention): '
            + mapping
        )
    lines += [
        "System note: reply ONLY to this exact message with:",
        "```bash",
        "printf '%%s\\n' \"<reply>\" | scripts/feishu-reply.sh %s %s --stdin" % (chat, mid),
        "```",
        "Do not reuse IDs from another message, and do not use cryo-agent send for Feishu replies.",
        "",
    ]
    _atomic_write(path, "\n".join(lines), mode=0o600)
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
                          "deadletter_after_sec": DEADLETTER_AFTER_SEC,
                          "context_messages": CONTEXT_MESSAGES,
                          "external_ack": ack_supported()}, indent=1))
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
