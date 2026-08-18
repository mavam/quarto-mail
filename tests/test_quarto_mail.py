from __future__ import annotations

import base64
import json
import os
from email import policy
from email.parser import BytesParser
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def run_quarto(
    *arguments: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["quarto", "render", *arguments],
        cwd=ROOT,
        env=env,
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
        ).replace(
            "](inline.png)",
            "](tests/fixtures/inline.png)",
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

        format_name = "mail-gog" if name == "reply" else "mail-gmail"
        result = run_quarto(str(self.source), "--to", format_name, "--output", "-")
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

    @property
    def eml(self) -> bytes:
        return (self.bundle / "message.eml").read_bytes()

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
        attachment_path = FIXTURES / "attachment~path~.txt"
        attachment = str(attachment_path.resolve())
        image_path = FIXTURES / "inline.png"

        self.assertTrue(message.preview.is_file())
        self.assertEqual(manifest["account"], "work@example.com")
        self.assertEqual(manifest["from"], "alias@example.com")
        self.assertEqual(manifest["from_name"], "Alex Example")
        self.assertEqual(
            manifest["to"],
            ["Customer Example <customer@example.com>"],
        )
        self.assertEqual(manifest["attachments"], [attachment])
        self.assertEqual(
            manifest["inline_images"],
            [{
                "source": str(image_path.resolve()),
                "filename": "inline.png",
                "content_type": "image/png",
                "content_id": "image-1@quarto-mail",
            }],
        )
        self.assertEqual(message.plain_output, message.body_text)
        self.assertIn("Hello,\n\nThe update includes:", message.body_text)
        self.assertIn("\n-- \nAlex Example\nRole\nExample Organization\n", message.body_text)
        self.assertTrue(message.body_html.startswith("<div>\n"))
        self.assertIn("<div>Hello,</div>", message.body_html)
        self.assertNotIn("<html", message.body_html)
        self.assertNotIn("<p>", message.body_html)
        self.assertIn('src="cid:image-1@quarto-mail"', message.body_html)
        self.assertIn('src="https://example.com/logo.png"', message.body_html)
        self.assertNotIn("mail-signature-separator", message.body_html)
        self.assertIn('<a href="https://example.com">', message.body_html)
        self.assertIn('<div>The update includes:</div>', message.body_html)
        self.assertIn('<ol type="1">', message.body_html)
        self.assertIn(
            "</ol>\n<div>Best,</div>",
            message.body_html,
        )
        self.assertNotIn("</ol>\n<div><br></div>", message.body_html)
        self.assertNotIn("class=", message.body_html)
        self.assertEqual(message.body_html.count("style="), 1)
        preview = message.preview.read_text(encoding="utf-8")
        self.assertNotIn("<style", preview)
        self.assertIn("tests/fixtures/inline.png", preview)
        self.assertIn("gmail.users.messages.send", message.command)
        self.assertIn("gmail-request.json", message.command)

        self.assertNotIn(b"\n", message.eml.replace(b"\r\n", b""))
        parsed = BytesParser(policy=policy.default).parsebytes(message.eml)
        self.assertEqual(parsed["Subject"], "Project üpdate")
        self.assertEqual(parsed["From"], "Alex Example <alias@example.com>")
        self.assertIsNotNone(parsed["Date"])
        self.assertRegex(parsed["Message-ID"], r"^<[0-9a-f]{64}@quarto-mail>$")
        self.assertEqual(parsed.get_content_type(), "multipart/mixed")
        alternative, attached = parsed.get_payload()
        self.assertEqual(alternative.get_content_type(), "multipart/alternative")
        plain, related = alternative.get_payload()
        self.assertEqual(plain.get_content().replace("\r\n", "\n"), message.body_text)
        self.assertEqual(related.get_content_type(), "multipart/related")
        html, inline = related.get_payload()
        self.assertEqual(html.get_content().replace("\r\n", "\n"), message.body_html)
        self.assertIn("cid:image-1@quarto-mail", html.get_content())
        self.assertIn("https://example.com/logo.png", html.get_content())
        self.assertEqual(inline["Content-ID"], "<image-1@quarto-mail>")
        self.assertEqual(inline.get_content_disposition(), "inline")
        self.assertEqual(inline.get_payload(decode=True), image_path.read_bytes())
        self.assertEqual(attached.get_filename(), attachment_path.name)
        self.assertEqual(attached.get_content_disposition(), "attachment")
        self.assertEqual(attached.get_payload(decode=True), attachment_path.read_bytes())
        self.assertNotIn("class=", html.get_content())
        self.assertNotIn("<style", html.get_content())

        request = json.loads(
            (message.bundle / "gmail-request.json").read_text(encoding="utf-8")
        )
        encoded = request["raw"]
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        self.assertEqual(decoded, message.eml)

        result = run_quarto(str(message.source), "--to", "mail-eml", "--output", "-")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.replace("\n", "\r\n").encode().rstrip(b"\r\n"),
            message.eml.rstrip(b"\r\n"),
        )

        first_eml = message.eml
        result = run_quarto(str(message.source), "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(message.eml, first_eml)

        result = run_quarto(str(message.source), "--to", "mail-gog", "--output", "-")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mail-gog does not support local inline images", result.stderr)

        no_inline = message.source.with_name(f"{message.source.stem}-gog.qmd")
        self.addCleanup(no_inline.unlink, missing_ok=True)
        no_inline.write_text(
            message.source.read_text(encoding="utf-8").replace(
                "![Pipeline diagram](tests/fixtures/inline.png)\n\n", ""
            ),
            encoding="utf-8",
        )
        no_inline_bundle = no_inline.with_suffix(".mail")
        self.addCleanup(shutil.rmtree, no_inline_bundle, True)
        result = run_quarto(str(no_inline), "--to", "mail-gog", "--output", "-")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--from 'alias@example.com'", result.stdout)
        self.assertIn("--body-html-file", result.stdout)
        self.assertIn(f"--attach '{attachment}'", result.stdout)

        fake_bin = Path(tempfile.mkdtemp(prefix="quarto-mail-python-"))
        self.addCleanup(shutil.rmtree, fake_bin, True)
        fake_python = fake_bin / "python3"
        fake_python.write_text("#!/bin/sh\necho 'synthetic MIME failure' >&2\nexit 3\n")
        fake_python.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
        result = run_quarto(str(message.source), env=environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MIME builder failed: synthetic MIME failure", result.stdout + result.stderr)
        self.assertFalse((message.bundle / "message.eml").exists())
        self.assertFalse((message.bundle / "gmail-request.json").exists())

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
        self.assertFalse((message.bundle / "message.eml").exists())
        self.assertFalse((message.bundle / "gmail-request.json").exists())
        result = run_quarto(str(message.source), "--to", "mail-eml", "--output", "-")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mail-eml does not support replies; use mail-gog", result.stderr)
        result = run_quarto(
            str(message.source), "--to", "mail-gmail", "--output", "-"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mail-gmail does not support replies; use mail-gog", result.stderr)

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
