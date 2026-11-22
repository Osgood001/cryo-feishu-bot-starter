import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "feishu_connector", ROOT / "connector" / "feishu_connector.py"
)
connector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(connector)


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        connector.CHAMBER = str(base)
        connector.INBOX = str(base / "messages" / "inbox")
        connector.OUTBOX = str(base / "messages" / "outbox")
        connector.ARCHIVE = str(base / "messages" / "outbox" / "archive")
        connector.QUARANTINE = str(base / "messages" / "outbox" / "quarantine")
        connector.STATE = str(base / ".connector")
        connector.LEDGER = str(base / ".connector" / "ledger")
        connector.SEEN = str(base / ".connector" / "seen")
        connector.BOT_NAME = "Helper"
        connector.BOT_OPEN_ID = "ou_Bot1234"
        connector.SIGNATURE = ""
        connector.DEADLETTER_AFTER_SEC = 10
        connector.CONTEXT_MESSAGES = 0
        connector._ACK_SUPPORTED = None
        connector._ensure_dirs()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def event(mid="om_Message1", chat="oc_Chat1", **updates):
        event = {
            "message_id": mid,
            "chat_id": chat,
            "chat_type": "p2p",
            "sender_type": "user",
            "sender_id": "ou_User1",
            "message_type": "text",
            "content": '{"text":"hello"}',
        }
        event.update(updates)
        return event

    def test_inbound_p2p_mention_thread_and_dedupe(self):
        path = connector.write_inbox(self.event(thread_id="omt_Thread1"))
        self.assertTrue(path)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("feishu_chat_id: oc_Chat1", text)
        self.assertIn("feishu_message_id: om_Message1", text)
        self.assertIn("feishu_thread_id: omt_Thread1", text)
        self.assertIsNone(connector.write_inbox(self.event()))

        ignored = self.event("om_Message2", chat_type="group", mentions=[])
        self.assertIsNone(connector.write_inbox(ignored))
        mentioned = self.event(
            "om_Message3", chat_type="group", mentions=[{"id": "ou_Bot1234"}]
        )
        self.assertTrue(connector.write_inbox(mentioned))

    def test_inbound_filters_invalid_bot_and_skipped_items(self):
        self.assertIsNone(connector.write_inbox(self.event(mid="bad")))
        self.assertIsNone(connector.write_inbox(self.event(sender_type="bot")))
        self.assertIsNone(connector.write_inbox(self.event(message_type="system")))

    def test_failed_inbox_write_is_recoverable_on_retry(self):
        original = connector._atomic_write
        calls = {"count": 0}

        def fail_once(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("simulated inbox write failure")
            return original(*args, **kwargs)

        with mock.patch.object(connector, "_atomic_write", side_effect=fail_once):
            with self.assertRaises(OSError):
                connector.write_inbox(self.event())
            self.assertTrue(connector.write_inbox(self.event()))

    def test_delivery_uses_exact_ids_signature_and_same_chat_fallback(self):
        connector.SIGNATURE = "-- bot"
        calls = []

        def send(args):
            calls.append(args)
            return "invalid_source" if len(calls) == 1 else "ok"

        with mock.patch.object(connector, "_send", side_effect=send):
            self.assertTrue(connector.deliver("oc_ExactChat", "om_ExactMessage", "body", "a" * 64))
        self.assertIn("+messages-reply", calls[0])
        self.assertEqual(calls[0][calls[0].index("--message-id") + 1], "om_ExactMessage")
        self.assertEqual(calls[0][calls[0].index("--markdown") + 1], "body\n\n-- bot")
        self.assertIn("+messages-send", calls[1])
        self.assertEqual(calls[1][calls[1].index("--chat-id") + 1], "oc_ExactChat")
        self.assertLessEqual(len(calls[1][calls[1].index("--idempotency-key") + 1]), 50)

    def test_delivered_ledger_retry_only_acknowledges(self):
        outbox = Path(connector.OUTBOX) / "reply.md"
        body = "one response"
        outbox.write_text(
            "---\nsource: feishu\nfeishu_chat_id: oc_Chat1\n"
            "feishu_message_id: om_Message1\n---\n\n" + body + "\n",
            encoding="utf-8",
        )
        _, ledger = connector._ledger_path("om_Message1", body)
        Path(ledger).write_text(
            json.dumps({"chat": "oc_Chat1", "message": "om_Message1", "state": "delivered"}),
            encoding="utf-8",
        )
        with mock.patch.object(connector, "deliver") as deliver, mock.patch.object(
            connector, "external_ack", return_value=True
        ) as ack:
            self.assertEqual(connector.process_outbox_once(), 1)
        deliver.assert_not_called()
        ack.assert_called_once_with("om_Message1")
        self.assertTrue((Path(connector.ARCHIVE) / "reply.md").exists())

    def test_invalid_and_expired_items_quarantine_with_local_notice(self):
        invalid = Path(connector.OUTBOX) / "invalid.md"
        invalid.write_text("not frontmatter", encoding="utf-8")
        self.assertEqual(connector.process_outbox_once(), 0)
        self.assertTrue((Path(connector.QUARANTINE) / invalid.name).exists())

        expired = Path(connector.OUTBOX) / "expired.md"
        expired.write_text(
            "---\nsource: feishu\nfeishu_chat_id: oc_Chat1\n"
            "feishu_message_id: om_Message1\n---\n\nresponse\n",
            encoding="utf-8",
        )
        old = time.time() - 20
        os.utime(expired, (old, old))
        with mock.patch.object(connector, "deliver", return_value=False), mock.patch.object(
            connector, "external_ack", return_value=True
        ) as ack:
            self.assertEqual(connector.process_outbox_once(), 0)
        ack.assert_called_once_with("om_Message1")
        self.assertTrue((Path(connector.QUARANTINE) / expired.name).exists())
        notices = list(Path(connector.INBOX).glob("*_delivery-failed.md"))
        self.assertEqual(len(notices), 1)
        self.assertIn("source: local", notices[0].read_text(encoding="utf-8"))

    def test_external_ack_already_unknown_and_unsupported(self):
        fake = ROOT / "tests" / "fakes" / "cryo-agent"
        connector.CRYO_AGENT = str(fake)
        with mock.patch.dict(os.environ, {"FAKE_CRYO_HELP_RC": "2"}, clear=False):
            connector._ACK_SUPPORTED = None
            self.assertFalse(connector.ack_supported())
            self.assertTrue(connector.external_ack("om_Message1"))

        cases = [
            ("matched=0, already=1, unknown=0", True),
            ("matched=0, already=0, unknown=1", False),
        ]
        for output, expected in cases:
            with self.subTest(output=output), mock.patch.dict(
                os.environ,
                {"FAKE_CRYO_HELP_RC": "0", "FAKE_CRYO_ACK_RC": "1", "FAKE_CRYO_ACK_OUTPUT": output},
                clear=False,
            ):
                connector._ACK_SUPPORTED = None
                self.assertEqual(connector.external_ack("om_Message1"), expected)

    def test_log_redacts_ids_and_secret_values(self):
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            connector.log("oc_SecretChat123", "om_SecretMessage123", "token=abcdefghijk")
        value = stream.getvalue()
        self.assertNotIn("SecretChat123", value)
        self.assertNotIn("SecretMessage123", value)
        self.assertNotIn("abcdefghijk", value)
        self.assertIn("<redacted>", value)

    def test_inbound_mentions_mapping_and_reply_command_hint(self):
        ev = self.event(
            mid="om_MentionMsg1",
            chat="oc_GroupChat1",
            chat_type="group",
            sender_name="Alice",
            parent_id="om_Parent1",
            content='{"text":"@_user_1 @_user_2 please review"}',
            mentions=[
                {"key": "@_user_1", "name": "Helper", "id": {"open_id": "ou_Bot1234"}},
                {"key": "@_user_2", "name": "Bob", "id": {"open_id": "ou_Bob5678"}},
                {"key": "@_user_3", "name": "Bob", "id": "ou_Bob5678"},
            ],
        )
        path = connector.write_inbox(ev)
        self.assertTrue(path)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("feishu_sender_name: Alice", text)
        self.assertIn("feishu_mentions: Bob=ou_Bob5678", text)
        self.assertIn("feishu_reply_to: om_Parent1", text)
        self.assertIn("@Helper @Bob please review", text)
        self.assertNotIn("@_user_2", text)
        self.assertNotIn("ou_Bot1234", text)
        self.assertIn('<at user_id="open_id">Name</at>', text)
        self.assertIn("Bob=ou_Bob5678", text)
        self.assertIn(
            "scripts/feishu-reply.sh oc_GroupChat1 om_MentionMsg1 --stdin", text
        )
        self.assertIn("do not use cryo-agent send", text)

    def test_inbound_post_rich_text_extraction(self):
        post_content = json.dumps({
            "zh_cn": {
                "title": "Release Check",
                "content": [
                    [
                        {"tag": "at", "user_name": "Helper"},
                        {"tag": "text", "text": " verify pipeline status"},
                    ]
                ],
            }
        })
        ev = self.event(
            mid="om_PostMsg1",
            chat="oc_GroupChat2",
            chat_type="group",
            message_type="post",
            content=post_content,
        )
        path = connector.write_inbox(ev)
        self.assertTrue(path)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("Release Check\n@Helper verify pipeline status", text)

    def test_inbound_thread_and_quoted_context_injection(self):
        connector.CONTEXT_MESSAGES = 10

        def fake_lark_json(*args, **_kwargs):
            if "+threads-messages-list" in args:
                return {
                    "data": {
                        "messages": [
                            {
                                "message_id": "om_Root1",
                                "sender": {"id": "ou_Alice1", "name": "Alice"},
                                "content": '{"text":"Can we ship build 7?"}',
                            },
                            {
                                "message_id": "om_BotReply1",
                                "sender": {"id": "ou_Bot1234"},
                                "content": '{"text":"Running checks now."}',
                            },
                            {
                                "message_id": "om_Followup1",
                                "sender": {"id": "ou_Alice1", "name": "Alice"},
                                "content": '{"text":"@Helper any update?"}',
                            },
                        ]
                    }
                }
            if "+messages-mget" in args:
                return {
                    "data": {
                        "messages": [
                            {
                                "message_id": "om_BotReply1",
                                "sender": {"id": "ou_Bot1234"},
                                "content": '{"text":"Running checks now."}',
                            }
                        ]
                    }
                }
            return None

        ev = self.event(
            mid="om_Followup1",
            chat="oc_GroupChat3",
            chat_type="group",
            thread_id="omt_Thread99",
            parent_id="om_BotReply1",
            content='{"text":"@Helper any update?"}',
        )
        with mock.patch.object(connector, "_lark_json", side_effect=fake_lark_json):
            path = connector.write_inbox(ev)
        self.assertTrue(path)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("System note: thread context (chronological", text)
        self.assertIn("> [Alice] Can we ship build 7?", text)
        self.assertIn("> [bot] Running checks now.", text)
        self.assertNotIn("> [Alice] @Helper any update?", text)
        self.assertIn("System note: quoted parent message", text)

    def test_inbound_p2p_recent_chat_chronological_and_non_fatal_failure(self):
        connector.CONTEXT_MESSAGES = 5

        def fake_chat(*args, **_kwargs):
            if "+chat-messages-list" in args:
                # Feishu returns newest-first for --order desc.
                return {
                    "data": {
                        "messages": [
                            {
                                "message_id": "om_P2pCur",
                                "sender": {"id": "ou_User1", "name": "User"},
                                "content": '{"text":"is it done?"}',
                            },
                            {
                                "message_id": "om_P2pPrev2",
                                "sender": {"id": "ou_Bot1234"},
                                "content": '{"text":"Second step running."}',
                            },
                            {
                                "message_id": "om_P2pPrev1",
                                "sender": {"id": "ou_User1", "name": "User"},
                                "content": '{"text":"First request."}',
                            },
                        ]
                    }
                }
            return None

        with mock.patch.object(connector, "_lark_json", side_effect=fake_chat):
            path = connector.write_inbox(
                self.event(mid="om_P2pCur", content='{"text":"is it done?"}')
            )
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("System note: recent chat context (chronological", text)
        self.assertLess(
            text.index("> [User] First request."),
            text.index("> [bot] Second step running."),
        )

        # Lookup errors must never block inbox delivery.
        with mock.patch.object(connector, "_lark_json", return_value=None):
            fallback_path = connector.write_inbox(
                self.event(mid="om_P2pFallback", content='{"text":"hello"}')
            )
        self.assertTrue(fallback_path)
        fallback_text = Path(fallback_path).read_text(encoding="utf-8")
        self.assertIn("scripts/feishu-reply.sh oc_Chat1 om_P2pFallback --stdin", fallback_text)


if __name__ == "__main__":
    unittest.main()
