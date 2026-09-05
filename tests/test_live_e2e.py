"""Opt-in live tests: set QUARTO_MAIL_LIVE=1 and QUARTO_MAIL_TEST_ADDRESS.

Sends three synthetic emails to that address and creates, updates, and removes
one test draft. Ordinary test discovery skips this class.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = os.environ.get("QUARTO_MAIL_TEST_ADDRESS")


@unittest.skipUnless(os.environ.get("QUARTO_MAIL_LIVE") == "1" and ADDRESS, "live Gmail tests require explicit opt-in")
class LiveMailTests(unittest.TestCase):
    def run_command(self, command):
        result = subprocess.run(command, cwd=self.project, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def api(self, method, params):
        result = json.loads(self.run_command([
            "gog", "--readonly", "--account", ADDRESS, "api", "call", "gmail", "v1", method,
            "--params", json.dumps({"userId": "me", **params}), "--no-input",
        ]))
        return result.get("result", result)

    def render(self, name, metadata, body):
        source = self.project / f"{name}.qmd"
        source.write_text(
            "---\nmail:\n  sender: self\n  to:\n    - " + ADDRESS + "\n"
            + metadata + "---\n\n" + body + "\n", encoding="utf-8",
        )
        preview = self.run_command(["quarto", "render", source.name, "--to", "mail-gog", "--output", "-"])
        self.assertIn(ADDRESS, preview)
        self.assertIn(body, preview)
        (self.project / f"{name}.preview.md").write_text(preview)
        return preview

    def deliver(self, name):
        result = json.loads(self.run_command(["sh", f"{name}.send.sh"]))
        result = result.get("result", result)
        self.assertIn("id", result)
        return result

    def verify_message(self, name, raw):
        actual = BytesParser(policy=default).parsebytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        expected = BytesParser(policy=default).parsebytes((self.project / f"{name}.mail" / "message.eml").read_bytes())
        self.assertEqual(str(actual["To"]), str(expected["To"]))
        self.assertEqual(str(actual["Subject"]), str(expected["Subject"]))
        self.assertEqual(str(actual["In-Reply-To"]), str(expected["In-Reply-To"]))
        for subtype in ("plain", "html"):
            self.assertEqual(
                actual.get_body(preferencelist=(subtype,)).get_content().replace("\r\n", "\n"),
                expected.get_body(preferencelist=(subtype,)).get_content().replace("\r\n", "\n"),
            )
        def attachments(msg):
            return [(part.get_filename(), part.get_payload(decode=True)) for part in msg.iter_attachments()]

        self.assertEqual(attachments(actual), attachments(expected))

    def test_render_send_reply_forward_and_drafts(self):
        with tempfile.TemporaryDirectory(prefix="quarto-mail-live-") as temporary:
            self.project = Path(temporary)
            shutil.copytree(ROOT / "_extensions", self.project / "_extensions")
            (self.project / "_quarto.yml").write_text("project:\n  type: default\n")
            (self.project / "_metadata.yml").write_text(
                "mail-profiles:\n  senders:\n    self:\n      account: " + ADDRESS
                + "\n      from: " + ADDRESS + "\n      name: Quarto Mail E2E\n"
            )
            subject = f"[quarto-mail E2E] {uuid.uuid4().hex[:12]}"
            seed_body = "Synthetic Quarto Mail end-to-end test. No action is needed."
            (self.project / "test.txt").write_text("Synthetic attachment bytes.\n")
            self.render("new", f"  subject: '{subject}'\n  attachments: [test.txt]\n", seed_body)
            new = self.deliver("new")
            self.verify_message("new", self.api("gmail.users.messages.get", {"id": new["id"], "format": "raw"})["raw"])

            reply_preview = self.render("reply", f"  reply-to-message-id: {new['id']}\n  quote: true\n", "Synthetic reply test.")
            self.assertIn(seed_body, reply_preview)
            reply = self.deliver("reply")
            self.assertEqual(reply["threadId"], new["threadId"])
            self.verify_message("reply", self.api("gmail.users.messages.get", {"id": reply["id"], "format": "raw"})["raw"])

            forward_preview = self.render("forward", f"  forward-message-id: {new['id']}\n", "Synthetic forward test.")
            self.assertIn(seed_body, forward_preview)
            self.assertIn("test.txt", forward_preview)
            forward = self.deliver("forward")
            self.verify_message("forward", self.api("gmail.users.messages.get", {"id": forward["id"], "format": "raw"})["raw"])

            self.render("draft", f"  subject: '{subject} draft'\n  delivery: draft\n", "Synthetic draft test.")
            draft = self.deliver("draft")
            try:
                self.render("draft", f"  subject: '{subject} draft'\n  delivery: draft\n  draft-id: {draft['id']}\n", "Updated synthetic draft test.")
                updated = self.deliver("draft")
                self.assertEqual(updated["id"], draft["id"])
                actual = self.api("gmail.users.drafts.get", {"id": draft["id"], "format": "raw"})
                self.verify_message("draft", actual["message"]["raw"])
            finally:
                self.run_command([
                    "gog", "--account", ADDRESS, "api", "call", "gmail", "v1", "gmail.users.drafts.delete",
                    "--params", json.dumps({"userId": "me", "id": draft["id"]}),
                    "--allow-write", "--force", "--no-input",
                ])
            print(json.dumps({"subject": subject, "new": new["id"], "reply": reply["id"], "forward": forward["id"], "draft": "created, updated, deleted"}))


if __name__ == "__main__":
    unittest.main()
