from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def run_quarto(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["quarto", "render", *arguments],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )


class RenderedMessage:
    def __init__(self, name: str):
        self.source = ROOT / f".quarto-mail-test-{uuid.uuid4()}.qmd"
        source = (FIXTURES / f"{name}.qmd").read_text(encoding="utf-8")
        source = source.replace(
            "- attachment~path~.txt",
            "- tests/fixtures/attachment~path~.txt",
        )
        self.source.write_text(source, encoding="utf-8")
        self.bundle = self.source.with_suffix(".mail")
        self.preview = self.source.with_suffix(".html")
        self.support = self.source.with_name(f"{self.source.stem}_files")

        result = run_quarto(str(self.source), "--quiet")
        if result.returncode != 0:
            self.cleanup()
            raise AssertionError(result.stderr)
        result = run_quarto(str(self.source), "--to", "mail-plain", "--output", "-")
        if result.returncode != 0:
            self.cleanup()
            raise AssertionError(result.stderr)
        self.plain_output = result.stdout

        result = run_quarto(str(self.source), "--to", "mail-gog", "--output", "-")
        if result.returncode != 0:
            self.cleanup()
            raise AssertionError(result.stderr)
        self.command = result.stdout

    @property
    def manifest(self) -> dict[str, object]:
        return json.loads((self.bundle / "manifest.json").read_text(encoding="utf-8"))

    @property
    def body_text(self) -> str:
        return (self.bundle / "body.txt").read_text(encoding="utf-8")

    @property
    def body_html(self) -> str:
        return (self.bundle / "body.html").read_text(encoding="utf-8")

    def cleanup(self) -> None:
        self.source.unlink(missing_ok=True)
        self.preview.unlink(missing_ok=True)
        shutil.rmtree(self.bundle, ignore_errors=True)
        shutil.rmtree(self.support, ignore_errors=True)


class QuartoMailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rendered: list[RenderedMessage] = []

    def tearDown(self) -> None:
        for message in self.rendered:
            message.cleanup()

    def render(self, name: str) -> RenderedMessage:
        message = RenderedMessage(name)
        self.rendered.append(message)
        return message

    def test_renders_a_complete_message(self) -> None:
        message = self.render("work")
        manifest = message.manifest
        attachment = str((FIXTURES / "attachment~path~.txt").resolve())

        self.assertTrue(message.preview.is_file())
        self.assertEqual(manifest["account"], "work@example.com")
        self.assertEqual(manifest["from"], "alias@example.com")
        self.assertEqual(
            manifest["to"],
            ["Customer Example <customer@example.com>"],
        )
        self.assertEqual(manifest["attachments"], [attachment])
        self.assertEqual(message.plain_output, message.body_text)
        self.assertIn("Hello,\n\nThe update includes:", message.body_text)
        self.assertIn("\n-- \nAlex Example\nRole\nExample Organization\n", message.body_text)
        self.assertTrue(message.body_html.startswith("<div>\n"))
        self.assertIn("<div>Hello,</div>", message.body_html)
        self.assertNotIn("<html", message.body_html)
        self.assertNotIn("<p>", message.body_html)
        self.assertNotIn("mail-signature-separator", message.body_html)
        self.assertIn('<a href="https://example.com">', message.body_html)
        self.assertIn(
            '<div>The update includes:</div>\n<ol type="1">',
            message.body_html,
        )
        self.assertIn(
            "</ol>\n<div>Best,</div>",
            message.body_html,
        )
        self.assertNotIn("</ol>\n<div><br></div>", message.body_html)
        self.assertNotIn("class=", message.body_html)
        self.assertEqual(message.body_html.count("style="), 1)
        self.assertNotIn("<style", message.preview.read_text(encoding="utf-8"))
        self.assertIn("--from 'alias@example.com'", message.command)
        self.assertIn("--body-html-file", message.command)
        self.assertIn(f"--attach '{attachment}'", message.command)

    def test_renders_and_executes_a_reply_command_once(self) -> None:
        message = self.render("reply")
        self.assertIsNone(message.manifest["subject"])
        self.assertEqual(message.manifest["reply_to_message_id"], "message-123")
        self.assertTrue(message.manifest["quote"])
        self.assertNotIn("--subject", message.command)
        self.assertNotIn("--from", message.command)
        self.assertIn("--reply-to-message-id 'message-123'", message.command)
        self.assertNotIn("mail-closing", message.body_html)
        self.assertIn("<div>Alex</div>", message.body_html)
        self.assertNotIn("\nBest,\n", message.body_text)
        self.assertTrue(message.body_text.endswith("\nAlex\n"))

        directory = Path(tempfile.mkdtemp(prefix="quarto-mail-gog-"))
        self.addCleanup(shutil.rmtree, directory, True)
        log = directory / "calls.log"
        fake = directory / "gog"
        fake.write_text(
            "#!/bin/sh\nprintf 'call\\n' >> \"$FAKE_GOG_LOG\"\n"
            "printf '{\"id\":\"fake\"}\\n'\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{directory}:{environment['PATH']}"
        environment["FAKE_GOG_LOG"] = str(log)
        result = subprocess.run(
            ["/bin/sh", "-c", message.command],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '{"id":"fake"}\n')
        self.assertEqual(log.read_text(encoding="utf-8"), "call\n")


if __name__ == "__main__":
    unittest.main()
