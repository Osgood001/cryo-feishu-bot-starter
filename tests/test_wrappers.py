import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
REPLY = ROOT / "scripts" / "feishu-reply.sh"
POST = ROOT / "scripts" / "proactive-post.sh"
FAKE_LARK = ROOT / "tests" / "fakes" / "lark-cli"


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.env = dict(os.environ)
        self.env.update(
            {"FEISHU_OUTBOX_DIR": str(self.base / "outbox"), "LARK_CLI": str(FAKE_LARK)}
        )

    def tearDown(self):
        self.temp.cleanup()

    def run_cmd(self, script, *args, input_text=None, env=None):
        return subprocess.run(
            [str(script), *args],
            input=input_text,
            text=True,
            capture_output=True,
            env=env or self.env,
            cwd=ROOT,
            check=False,
        )

    def test_reply_validates_ids(self):
        self.assertEqual(self.run_cmd(REPLY, "bad", "om_Message1", "text").returncode, 2)
        self.assertEqual(self.run_cmd(REPLY, "oc_Chat1", "bad", "text").returncode, 2)

    def test_reply_stdin_atomic_mode_0600(self):
        result = self.run_cmd(
            REPLY, "oc_Chat1", "om_Message1", "--stdin", input_text="line one\nline two\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        files = list((self.base / "outbox").glob("*.md"))
        self.assertEqual(len(files), 1)
        self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
        self.assertEqual(list((self.base / "outbox").glob(".tmp*")), [])
        text = files[0].read_text(encoding="utf-8")
        self.assertIn("source: feishu", text)
        self.assertIn("line one\nline two", text)

    def test_operator_user_and_chat_routing(self):
        log = self.base / "lark.jsonl"
        env = dict(self.env, FAKE_LARK_LOG=str(log))
        for mode, target, flag in [
            ("--user", "ou_Operator1", "--user-id"),
            ("--chat", "oc_StatusChat1", "--chat-id"),
        ]:
            with self.subTest(mode=mode):
                result = self.run_cmd(POST, mode, target, "status", env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(calls[0][calls[0].index("--user-id") + 1], "ou_Operator1")
        self.assertEqual(calls[1][calls[1].index("--chat-id") + 1], "oc_StatusChat1")

    def test_operator_stdin_and_validation(self):
        log = self.base / "lark.jsonl"
        env = dict(self.env, FAKE_LARK_LOG=str(log))
        result = self.run_cmd(POST, "--user", "ou_Operator1", "--stdin", input_text="two\nlines", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        call = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(call[call.index("--markdown") + 1], "two\nlines")
        self.assertEqual(self.run_cmd(POST, "--user", "oc_WrongKind", "text").returncode, 2)

    def test_dry_run_exposes_neither_target_nor_body(self):
        body = "PRIVATE_MESSAGE_BODY_123"
        env = dict(self.env, DRY_RUN="1", FAKE_LARK_LOG=str(self.base / "must-not-exist"))
        result = self.run_cmd(POST, "--user", "ou_Operator1", body, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        combined = result.stdout + result.stderr
        self.assertNotIn(body, combined)
        self.assertNotIn("ou_Operator1", combined)
        self.assertFalse((self.base / "must-not-exist").exists())


if __name__ == "__main__":
    unittest.main()
