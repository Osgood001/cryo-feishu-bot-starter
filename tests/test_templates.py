import os
from pathlib import Path
import re
import stat
import subprocess
import unittest
import configparser


ROOT = Path(__file__).resolve().parents[1]


class TemplateTests(unittest.TestCase):
    def test_required_templates_exist_and_are_sanitized(self):
        required = [
            ".env.example",
            "templates/systemd/feishu-connector.service",
            "templates/supervisord/feishu-connector.conf",
            "templates/crontab.active-node.example",
            "templates/ssh/config.example",
            "templates/ssh/known-hosts-setup.sh",
        ]
        for name in required:
            with self.subTest(name=name):
                path = ROOT / name
                self.assertTrue(path.is_file())
                content = path.read_text(encoding="utf-8")
                self.assertNotRegex(content, r"/home/[A-Za-z0-9._-]+/")
                self.assertNotRegex(content, r"\b(?:ou|oc|om)_[A-Za-z0-9]{20,}\b")
                self.assertNotIn("StrictHostKeyChecking no", content)

    def test_env_covers_connector_and_wrapper_contract(self):
        env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
        names = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", env_text, re.MULTILINE))
        required = {
            "CHAMBER_DIR", "CONNECTOR_STATE_DIR", "LARK_CLI", "LARK_CLI_PROFILE",
            "CRYO_AGENT", "FEISHU_BOT_NAME", "FEISHU_BOT_OPEN_ID", "BOT_SIGNATURE",
            "OUTBOX_POLL_SEC", "DEADLETTER_AFTER_SEC", "MAX_REPLY_CHARS",
            "FEISHU_OUTBOX_DIR", "LARK_CLI_IDENTITY", "OPERATOR_OPEN_ID",
            "DEFAULT_FEISHU_CHAT_ID", "FEISHU_SCAN_AS_PRIMARY", "FEISHU_SCAN_AS_FALLBACK",
        }
        self.assertEqual(required - names, set())
        connector = (ROOT / "connector/feishu_connector.py").read_text(encoding="utf-8")
        connector_vars = set(re.findall(r'ENV\.get\("([A-Z][A-Z0-9_]*)"', connector))
        self.assertEqual(connector_vars - names, set())
        defaults = {
            "OUTBOX_POLL_SEC", "DEADLETTER_AFTER_SEC", "MAX_REPLY_CHARS",
            "LARK_CLI_IDENTITY", "FEISHU_SCAN_AS_PRIMARY", "FEISHU_SCAN_AS_FALLBACK",
        }
        for line in env_text.splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                self.assertTrue(value, key)
                if key not in defaults:
                    self.assertIn("REPLACE_WITH_", value, key)

    def test_service_templates_match_real_entrypoint(self):
        systemd = (ROOT / "templates/systemd/feishu-connector.service").read_text()
        supervisor = (ROOT / "templates/supervisord/feishu-connector.conf").read_text()
        for content in (systemd, supervisor):
            self.assertIn("connector/feishu_connector.py run", content)
            self.assertIn("CHAMBER", content)
        parser = configparser.RawConfigParser()
        parser.read_string(supervisor)
        section = "program:cryo-feishu-connector"
        self.assertTrue(parser.has_section(section))
        supervisor_vars = set(re.findall(r'([A-Z][A-Z0-9_]*)="', parser.get(section, "environment")))
        connector = (ROOT / "connector/feishu_connector.py").read_text(encoding="utf-8")
        connector_vars = set(re.findall(r'ENV\.get\("([A-Z][A-Z0-9_]*)"', connector))
        self.assertEqual(connector_vars - supervisor_vars, set())
        cron = (ROOT / "templates/crontab.active-node.example").read_text()
        self.assertLess(cron.index(".active-node"), cron.index("REPLACE_WITH_BOUNDED_COMMAND"))
        self.assertIn("flock -n", cron)
        self.assertIn("timeout 15m", cron)

    def test_ssh_workflow_is_strict_and_executable(self):
        config = (ROOT / "templates/ssh/config.example").read_text()
        self.assertIn("StrictHostKeyChecking yes", config)
        self.assertIn("IdentitiesOnly yes", config)
        script = ROOT / "templates/ssh/known-hosts-setup.sh"
        self.assertTrue(stat.S_IMODE(script.stat().st_mode) & stat.S_IXUSR)
        subprocess.run(["bash", "-n", str(script)], check=True)

    def test_fake_only_smoke(self):
        env = dict(os.environ)
        env["PATH"] = "/usr/bin:/bin"
        result = subprocess.run(
            [str(ROOT / "scripts" / "smoke-test.sh")], cwd=ROOT, env=env,
            text=True, capture_output=True, check=False, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("fake-only", result.stdout)
        self.assertIn("network=none", result.stdout)

    def test_public_docs_link_artifacts_and_state_boundaries(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)]+\.md)\)", readme):
            self.assertTrue((ROOT / link).is_file(), link)
        combined = "\n".join(
            (ROOT / name).read_text(encoding="utf-8")
            for name in ["README.md", "docs/feishu-routing.md", "docs/operations.md"]
        )
        for phrase in [
            "Public Cryochamber v0.2.6", "No inbound polling fallback",
            "own-thread routing", "does **not** ship an `ops/dispatch` runner or watchdog",
        ]:
            self.assertIn(phrase, combined)
        self.assertIn("npx @larksuite/cli@latest install", readme)
        self.assertIn('--scope "im:message.send_as_user im:message" --no-wait --json', readme)
        self.assertIn("auth qrcode '<verification_url>' --output auth-qr.png", readme)
        self.assertIn("--device-code '<device_code>'", readme)
        self.assertIn("must not run\n`auth login`", readme)
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertGreaterEqual(agents.count("--stdin"), 2)
        credentials = (ROOT / "docs/credentials.md").read_text(encoding="utf-8")
        self.assertIn("does not prove server-side", credentials)
        connector = (ROOT / "connector/feishu_connector.py").read_text(encoding="utf-8")
        self.assertNotIn("templates/connector.env.example", connector)


if __name__ == "__main__":
    unittest.main()
