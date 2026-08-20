from __future__ import annotations

import base64
import json
import os
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
import shutil
import subprocess
import tempfile
import unittest
import uuid
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
GMAIL_RESPONSE = FIXTURES / "gmail-message.json"


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


def parse_message(raw: bytes):
    return BytesParser(policy=policy.default).parsebytes(raw)


class RenderedMessage:
    def __init__(
        self,
        name: str,
        transform: Callable[[str], str] | None = None,
    ):
        self.source = ROOT / f".quarto-mail-test-{uuid.uuid4()}.qmd"
        source = (FIXTURES / f"{name}.qmd").read_text(encoding="utf-8")
        source = source.replace(
            "- attachment~path~.txt",
            "- tests/fixtures/attachment~path~.txt",
        ).replace(
            "](inline.png)",
            "](tests/fixtures/inline.png)",
        )
        if transform is not None:
            source = transform(source)
        self.source.write_text(source, encoding="utf-8")
        os.utime(self.source, (1_700_000_000, 1_700_000_000))
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

    @property
    def eml(self) -> bytes:
        return (self.bundle / "message.eml").read_bytes()

    @property
    def request(self) -> dict[str, str]:
        return json.loads((self.bundle / "gmail-request.json").read_text(encoding="utf-8"))

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

    def render(
        self,
        name: str,
        transform: Callable[[str], str] | None = None,
    ) -> RenderedMessage:
        message = RenderedMessage(name, transform)
        self.rendered.append(message)
        return message

    def fake_gog(self) -> tuple[dict[str, str], Path]:
        directory = Path(tempfile.mkdtemp(prefix="quarto-mail-gog-"))
        self.addCleanup(shutil.rmtree, directory, True)
        log = directory / "calls.log"
        fake = directory / "gog"
        fake.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$FAKE_GOG_LOG\"\n"
            "case \"$*\" in\n"
            "  *gmail.users.messages.get*) cat \"$FAKE_GMAIL_RESPONSE\" ;;\n"
            "  *gmail.users.messages.send*) printf '{\"id\":\"sent-once\"}\\n' ;;\n"
            "  *) printf 'unexpected gog call\\n' >&2; exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{directory}:{environment['PATH']}"
        environment["FAKE_GOG_LOG"] = str(log)
        environment["FAKE_GMAIL_RESPONSE"] = str(GMAIL_RESPONSE)
        return environment, log

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
        self.assertEqual(manifest["to"], ["Customer Example <customer@example.com>"])
        self.assertEqual(manifest["attachments"], [attachment])
        self.assertEqual(manifest["cc"], ["Colleague Example <colleague@example.com>"])
        self.assertEqual(manifest["bcc"], ["Archive Example <archive@example.com>"])
        self.assertNotIn("quote", manifest)
        manifest_bytes = (message.bundle / "manifest.json").read_bytes()
        self.assertIn("Project üpdate".encode(), manifest_bytes)
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
        self.assertIn("</ol>\n<div>Best,</div>", message.body_html)
        self.assertNotIn("</ol>\n<div><br></div>", message.body_html)
        self.assertNotIn("class=", message.body_html)
        self.assertEqual(message.body_html.count("style="), 1)
        preview = message.preview.read_text(encoding="utf-8")
        self.assertNotIn("<style", preview)
        self.assertIn("tests/fixtures/inline.png", preview)

        self.assertIn("gmail.users.messages.send", message.command)
        self.assertIn("gmail-request.json", message.command)
        self.assertNotIn("gmail" + " send", message.command)
        self.assertFalse((message.bundle / "prepare.sh").exists())
        self.assertNotIn(b"\n", message.eml.replace(b"\r\n", b""))

        parsed = parse_message(message.eml)
        self.assertEqual(parsed["Subject"], "Project üpdate")
        self.assertEqual(parsed["From"], "Alex Example <alias@example.com>")
        self.assertEqual(parsed["To"], "Customer Example <customer@example.com>")
        self.assertEqual(parsed["Cc"], "Colleague Example <colleague@example.com>")
        self.assertEqual(parsed["Bcc"], "Archive Example <archive@example.com>")
        self.assertIsNotNone(parsed["Date"])
        self.assertRegex(parsed["Message-ID"], r"^<[0-9a-f]{64}@quarto-mail>$")
        self.assertEqual(parsed.get_content_type(), "multipart/mixed")
        alternative, attached = parsed.get_payload()
        self.assertEqual(alternative.get_content_type(), "multipart/alternative")
        plain, related = alternative.get_payload()
        self.assertEqual(plain.get_content().replace("\r\n", "\n"), message.body_text)
        self.assertEqual(related.get_content_type(), "multipart/related")
        html_part, inline = related.get_payload()
        self.assertEqual(html_part.get_content().replace("\r\n", "\n"), message.body_html)
        self.assertIn("cid:image-1@quarto-mail", html_part.get_content())
        self.assertIn("https://example.com/logo.png", html_part.get_content())
        self.assertEqual(inline["Content-ID"], "<image-1@quarto-mail>")
        self.assertEqual(inline.get_content_disposition(), "inline")
        self.assertEqual(inline.get_payload(decode=True), image_path.read_bytes())
        self.assertEqual(attached.get_filename(), attachment_path.name)
        self.assertEqual(attached.get_content_disposition(), "attachment")
        self.assertEqual(attached.get_payload(decode=True), attachment_path.read_bytes())

        encoded = message.request["raw"]
        decoded = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        self.assertEqual(decoded, message.eml)
        self.assertNotIn("threadId", message.request)

        eml_output = message.source.with_name(f"{message.source.stem}.output.eml")
        self.addCleanup(eml_output.unlink, missing_ok=True)
        result = run_quarto(
            str(message.source),
            "--to",
            "mail-eml",
            "--output",
            eml_output.name,
            "--quiet",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(eml_output.read_bytes(), message.eml)
        first_eml = message.eml
        first_request = (message.bundle / "gmail-request.json").read_bytes()
        first_manifest = (message.bundle / "manifest.json").read_bytes()
        result = run_quarto(str(message.source), "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(message.eml, first_eml)
        self.assertEqual((message.bundle / "gmail-request.json").read_bytes(), first_request)
        self.assertEqual((message.bundle / "manifest.json").read_bytes(), first_manifest)

        source_files = list((ROOT / "_extensions" / "mail").glob("*")) + [ROOT / "README.md"]
        for path in source_files:
            if path.is_file():
                self.assertNotIn("gog gmail" + " send", path.read_text(encoding="utf-8"))

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

    def test_prepares_and_sends_raw_replies(self) -> None:
        message = self.render("reply")
        image_path = FIXTURES / "inline.png"
        attachment_path = FIXTURES / "attachment~path~.txt"
        self.assertNotIn("subject", message.manifest)
        self.assertEqual(message.manifest["reply_to_message_id"], "message-123")
        self.assertTrue(message.manifest["quote"])
        self.assertIn("gmail.users.messages.send", message.command)
        self.assertNotIn("gmail" + " send", message.command)
        self.assertIn("gmail-request.json", message.command)
        self.assertFalse((message.bundle / "message.eml").exists())
        self.assertFalse((message.bundle / "gmail-request.json").exists())
        preparation = message.bundle / "prepare.sh"
        self.assertTrue(preparation.is_file())
        preparation_text = preparation.read_text(encoding="utf-8")
        self.assertIn("gmail.users.messages.get", preparation_text)
        self.assertIn('"format":"raw"', preparation_text)
        self.assertNotIn("gmail.users.messages.send", preparation_text)
        self.assertNotIn("--allow-write", preparation_text)

        environment, log = self.fake_gog()
        result = subprocess.run(
            ["/bin/sh", "-c", message.command],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("reply artifacts are not prepared", result.stderr)
        self.assertFalse(log.exists())

        result = subprocess.run(
            ["/bin/sh", str(preparation)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls_before_send = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls_before_send), 1)
        self.assertIn("gmail.users.messages.get", calls_before_send[0])
        self.assertNotIn("gmail.users.messages.send", "\n".join(calls_before_send))

        first_eml = message.eml
        first_request = (message.bundle / "gmail-request.json").read_bytes()
        first_reply = (message.bundle / "reply.json").read_bytes()
        parsed = parse_message(first_eml)
        self.assertEqual(parsed["Subject"], "Re: Original üpdate")
        self.assertEqual(parsed["In-Reply-To"], "<original-123@example.com>")
        self.assertEqual(
            parsed["References"],
            "<root@example.com> <previous@example.com> <original-123@example.com>",
        )
        self.assertEqual(parsed["To"], "Original Sender <sender@example.com>")
        self.assertEqual(parsed["Cc"], "Other Participant <participant@example.com>")
        self.assertEqual(parsed["Bcc"], "Archive Example <archive@example.com>")
        self.assertEqual(parsed.get_content_type(), "multipart/mixed")
        alternative, attached = parsed.get_payload()
        plain, related = alternative.get_payload()
        html_part, inline, quoted_inline = related.get_payload()
        plain_content = plain.get_content().replace("\r\n", "\n")
        html_content = html_part.get_content().replace("\r\n", "\n")
        self.assertIn("Thank you for your message.", plain_content)
        self.assertIn("On Tue, 12 Aug 2025 10:30:00 +0200, Sender Ü", plain_content)
        self.assertIn("> Original plain body.\n> Second line.", plain_content)
        self.assertIn('class="gmail_quote"', html_content)
        self.assertIn("Original <strong>HTML</strong> body.", html_content)
        self.assertIn("cid:quoted-1-", html_content)
        self.assertEqual(inline["Content-ID"], "<image-1@quarto-mail>")
        self.assertEqual(inline.get_payload(decode=True), image_path.read_bytes())
        self.assertRegex(quoted_inline["Content-ID"], r"^<quoted-1-[0-9a-f]{16}@quarto-mail>$")
        self.assertEqual(quoted_inline.get_filename(), "original-inline.png")
        self.assertEqual(quoted_inline.get_payload(decode=True), image_path.read_bytes())
        self.assertEqual(attached.get_payload(decode=True), attachment_path.read_bytes())
        self.assertEqual(message.request["threadId"], "thread-456")
        encoded = message.request["raw"]
        self.assertEqual(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)),
            first_eml,
        )
        reply_metadata = json.loads(first_reply)
        self.assertEqual(reply_metadata["thread_id"], "thread-456")
        self.assertEqual(reply_metadata["message_id"], "<original-123@example.com>")

        result = run_quarto(str(message.source), "--to", "mail-eml", "--output", "-")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(message.eml, first_eml)
        result = subprocess.run(
            ["/bin/sh", str(preparation)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(message.eml, first_eml)
        self.assertEqual((message.bundle / "gmail-request.json").read_bytes(), first_request)
        self.assertEqual((message.bundle / "reply.json").read_bytes(), first_reply)

        replacement = self.render(
            "reply",
            lambda source: source.replace(
                "  attachments:\n",
                "  subject: Replacement ✓\n  attachments:\n",
            ).replace("  quote: true", "  quote: false"),
        )
        replacement_preparation = replacement.bundle / "prepare.sh"
        result = subprocess.run(
            ["/bin/sh", str(replacement_preparation)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        replacement_parsed = parse_message(replacement.eml)
        self.assertEqual(replacement_parsed["Subject"], "Replacement ✓")
        self.assertEqual(replacement_parsed["In-Reply-To"], "<original-123@example.com>")
        self.assertEqual(replacement.request["threadId"], "thread-456")
        replacement_plain = next(
            part for part in replacement_parsed.walk() if part.get_content_type() == "text/plain"
        ).get_content()
        replacement_html = next(
            part for part in replacement_parsed.walk() if part.get_content_type() == "text/html"
        ).get_content()
        self.assertNotIn("Original plain body", replacement_plain)
        self.assertNotIn("gmail_quote", replacement_html)
        replacement_parts = list(replacement_parsed.walk())
        self.assertTrue(any(part.get_content_disposition() == "inline" for part in replacement_parts))
        self.assertTrue(any(part.get_content_disposition() == "attachment" for part in replacement_parts))

        calls_before_actual_send = log.read_text(encoding="utf-8")
        self.assertNotIn("gmail.users.messages.send", calls_before_actual_send)
        result = subprocess.run(
            ["/bin/sh", "-c", message.command],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '{"id":"sent-once"}\n')
        calls = log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum("gmail.users.messages.send" in call for call in calls), 1)

        invalid_response = message.bundle / "invalid-response.json"
        invalid_response.write_text("{}\n", encoding="utf-8")
        result = subprocess.run(
            [
                "python3",
                str(ROOT / "_extensions" / "mail" / "mime.py"),
                "prepare",
                str(message.bundle),
                str(invalid_response),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing a raw RFC message", result.stderr)
        self.assertFalse((message.bundle / "message.eml").exists())
        self.assertFalse((message.bundle / "gmail-request.json").exists())
        self.assertFalse((message.bundle / "reply.json").exists())

    def test_forwards_messages_and_creates_or_updates_drafts(self) -> None:
        message = self.render(
            "reply",
            lambda source: source.replace(
                "  reply-to-message-id: message-123\n  quote: true",
                "  forward-message-id: message-123\n  delivery: draft",
            ),
        )
        preparation = message.bundle / "prepare.sh"

        result = subprocess.run(
            ["/bin/sh", "-c", message.command],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forward artifacts are not prepared; run", result.stderr)
        self.assertIn(str(preparation), result.stderr)
        result = run_quarto(str(message.source), "--to", "mail-eml", "--output", "-")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "forward artifacts are not prepared; run",
            result.stdout + result.stderr,
        )

        result = subprocess.run(
            [
                "python3",
                str(ROOT / "_extensions" / "mail" / "mime.py"),
                "prepare",
                str(message.bundle),
                str(GMAIL_RESPONSE),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = parse_message(message.eml)
        self.assertEqual(parsed["Subject"], "Fwd: Original üpdate")
        self.assertIsNone(parsed["In-Reply-To"])
        plain = next(
            part for part in parsed.walk() if part.get_content_type() == "text/plain"
        ).get_content()
        html_body = next(
            part for part in parsed.walk() if part.get_content_type() == "text/html"
        ).get_content()
        self.assertIn("Forwarded message", plain)
        self.assertIn("Original plain body", plain)
        self.assertIn("Cc: Other Participant <participant@example.com>", plain)
        self.assertIn("Cc: Other Participant &lt;participant@example.com&gt;", html_body)
        self.assertIn("cid:quoted-1-", html_body)
        forwarded_inline = [
            part
            for part in parsed.walk()
            if str(part.get("Content-ID", "")).startswith("<quoted-1-")
        ]
        self.assertEqual(len(forwarded_inline), 1)
        self.assertEqual(
            forwarded_inline[0].get_payload(decode=True),
            (FIXTURES / "inline.png").read_bytes(),
        )
        draft_request = json.loads(
            (message.bundle / "gmail-draft-request.json").read_text()
        )
        self.assertEqual(draft_request["message"], message.request)
        self.assertIn("gmail.users.drafts.create", message.command)
        preparation_state = json.loads(
            (message.bundle / "reply.json").read_text(encoding="utf-8")
        )
        self.assertEqual(preparation_state["operation"], "forward")
        self.assertEqual(preparation_state["gmail_message_id"], "message-123")

        preserved_artifacts = {
            name: (message.bundle / name).read_bytes()
            for name in (
                "message.eml",
                "gmail-request.json",
                "gmail-draft-request.json",
                "reply.json",
            )
        }
        result = run_quarto(str(message.source), "--quiet")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name, contents in preserved_artifacts.items():
            self.assertEqual((message.bundle / name).read_bytes(), contents, name)

        updated = self.render(
            "work",
            lambda source: source.replace(
                "  subject: Project üpdate",
                "  subject: Project üpdate\n  delivery: draft\n  draft-id: draft-123",
            ),
        )
        self.assertIn("gmail.users.drafts.update", updated.command)
        self.assertIn("draft-123", updated.command)

    def test_forwards_filename_attachments_without_content_disposition(self) -> None:
        message = self.render(
            "reply",
            lambda source: source.replace(
                "  reply-to-message-id: message-123\n  quote: true",
                "  forward-message-id: message-123",
            ),
        )
        original = EmailMessage(policy=policy.SMTP)
        original["From"] = "Sender <sender@example.com>"
        original["To"] = "Recipient <recipient@example.com>"
        original["Subject"] = "Original attachments"
        original["Message-ID"] = "<original-attachments@example.com>"
        original["Date"] = "Tue, 12 Aug 2025 10:30:00 +0200"
        original.set_content("Original plain body.")
        original.add_alternative(
            '<div>Original HTML body.</div><img src="cid:related@example.com">',
            subtype="html",
        )
        related = original.get_payload()[-1]
        related.add_related(
            b"related-image",
            maintype="image",
            subtype="png",
            cid="<related@example.com>",
            filename="related.png",
        )
        related_image = related.get_payload()[-1]
        del related_image["Content-Disposition"]
        related_image.set_param("name", "related.png", header="Content-Type")

        attachment = EmailMessage(policy=policy.SMTP)
        attachment.set_content(
            b"attachment-without-disposition",
            maintype="application",
            subtype="octet-stream",
        )
        attachment.set_param(
            "name",
            "without-disposition.bin",
            header="Content-Type",
        )
        original.make_mixed()
        original.attach(attachment)
        response = {
            "id": "message-123",
            "threadId": "thread-attachments",
            "raw": base64.urlsafe_b64encode(original.as_bytes())
            .rstrip(b"=")
            .decode("ascii"),
        }
        response_path = message.bundle / "attachment-response.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")

        result = subprocess.run(
            [
                "python3",
                str(ROOT / "_extensions" / "mail" / "mime.py"),
                "prepare",
                str(message.bundle),
                str(response_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = parse_message(message.eml)
        matching_parts = [
            part
            for part in parsed.walk()
            if part.get_payload(decode=True)
            in {b"related-image", b"attachment-without-disposition"}
        ]
        self.assertEqual(len(matching_parts), 2)
        related_part = next(
            part
            for part in matching_parts
            if part.get_payload(decode=True) == b"related-image"
        )
        attachment_part = next(
            part
            for part in matching_parts
            if part.get_payload(decode=True) == b"attachment-without-disposition"
        )
        self.assertEqual(related_part.get_content_disposition(), "inline")
        self.assertRegex(str(related_part["Content-ID"]), r"^<quoted-1-")
        self.assertEqual(attachment_part.get_filename(), "without-disposition.bin")
        self.assertEqual(attachment_part.get_content_disposition(), "attachment")

    def test_derives_reply_all_recipients(self) -> None:
        message = self.render(
            "reply",
            lambda source: source.replace(
                "  to:\n    - Original Sender <sender@example.com>\n  cc:\n    - Other Participant <participant@example.com>",
                "  reply-all: true",
            ),
        )
        result = subprocess.run(
            ["python3", str(ROOT / "_extensions" / "mail" / "mime.py"), "prepare", str(message.bundle), str(GMAIL_RESPONSE)],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = parse_message(message.eml)
        self.assertEqual(parsed["To"], "Sender Ü <sender@example.com>")
        self.assertEqual(parsed["Cc"], "Other Participant <participant@example.com>")

    def test_accepts_quoted_commas_and_unicode_display_names(self) -> None:
        message = self.render(
            "work",
            lambda source: source.replace(
                "Customer Example <customer@example.com>",
                "'\"Müller, Élodie\" <customer@example.com>'",
            ),
        )

        parsed = parse_message(message.eml)
        self.assertEqual(parsed["To"], '"Müller, Élodie" <customer@example.com>')

    def test_accepts_named_gog_account_identity(self) -> None:
        message = self.render(
            "work",
            lambda source: source.replace(
                "mail:\n",
                "mail-profiles:\n"
                "  senders:\n"
                "    work:\n"
                "      account: named-work\n"
                "      from: alias@example.com\n"
                "      name: Alex Example\n"
                "mail:\n",
            ).replace("  identity: work\n", "").replace("  signature: work\n", ""),
        )

        self.assertEqual(message.manifest["account"], "named-work")
        self.assertIn("--account 'named-work'", message.command)

    def test_uses_identity_as_default_sender_name(self) -> None:
        message = self.render(
            "work",
            lambda source: source.replace(
                "mail:\n",
                "mail-profiles:\n"
                "  senders:\n"
                "    work:\n"
                "      account: work@example.com\n"
                "      from: alias@example.com\n"
                "  identities:\n"
                "    work:\n"
                "      name: Alex Example\n"
                "  signatures:\n"
                "    work:\n"
                "      plain: Alex Example\n"
                "mail:\n",
            ),
        )

        self.assertEqual(message.manifest["from_name"], "Alex Example")
        self.assertEqual(parse_message(message.eml)["From"], "Alex Example <alias@example.com>")

    def test_rejects_invalid_mailboxes_before_reply_preparation(self) -> None:
        cases = {
            "multiple mailboxes": "first@example.com, second@example.com",
            "malformed mailbox": "not-an-address",
            "header injection": "customer@example.com\\n    Bcc: attacker@example.com",
        }
        for label, mailbox in cases.items():
            with self.subTest(label=label):
                source = ROOT / f".quarto-mail-invalid-{uuid.uuid4()}.qmd"
                bundle = source.with_suffix(".mail")
                preview = source.with_suffix(".html")
                support = source.with_name(f"{source.stem}_files")
                self.addCleanup(source.unlink, missing_ok=True)
                self.addCleanup(preview.unlink, missing_ok=True)
                self.addCleanup(shutil.rmtree, bundle, True)
                self.addCleanup(shutil.rmtree, support, True)
                contents = (FIXTURES / "reply.qmd").read_text(encoding="utf-8")
                contents = contents.replace(
                    "Original Sender <sender@example.com>",
                    mailbox,
                ).replace(
                    "- attachment~path~.txt",
                    "- tests/fixtures/attachment~path~.txt",
                ).replace(
                    "](inline.png)",
                    "](tests/fixtures/inline.png)",
                )
                source.write_text(contents, encoding="utf-8")

                result = run_quarto(str(source))

                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(
                    result.stdout + result.stderr,
                    r"invalid mailbox|must (?:contain single-line values|not contain empty values)",
                )
                self.assertFalse((bundle / "prepare.sh").exists())
                self.assertFalse((bundle / "message.eml").exists())

    def test_removes_stale_artifacts_after_failed_render(self) -> None:
        message = self.render("work")
        source = message.source.read_text(encoding="utf-8")
        message.source.write_text(
            source.replace("  subject: Project üpdate\n", ""),
            encoding="utf-8",
        )

        result = run_quarto(str(message.source))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "missing required metadata field 'mail.subject'",
            result.stdout + result.stderr,
        )
        for name in ("message.eml", "gmail-request.json", "reply.json", "prepare.sh"):
            self.assertFalse((message.bundle / name).exists(), name)

    def test_invalidates_prepared_reply_after_builder_change(self) -> None:
        message = self.render("reply")
        builder = ROOT / "_extensions" / "mail" / "mime.py"
        result = subprocess.run(
            ["python3", str(builder), "prepare", str(message.bundle), str(GMAIL_RESPONSE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((message.bundle / "message.eml").is_file())

        with tempfile.TemporaryDirectory(prefix="quarto-mail-builder-") as directory:
            changed_builder = Path(directory) / "mime.py"
            changed_builder.write_bytes(builder.read_bytes() + b"\n# synthetic builder change\n")
            result = subprocess.run(
                ["python3", str(changed_builder), "render", str(message.bundle)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((message.bundle / "prepare.sh").is_file())
        for name in ("message.eml", "gmail-request.json", "reply.json"):
            self.assertFalse((message.bundle / name).exists(), name)

    def test_rewrites_complete_quoted_content_ids(self) -> None:
        message = self.render("reply")
        original = EmailMessage(policy=policy.SMTP)
        original["From"] = "Sender <sender@example.com>"
        original["To"] = "matthias@vallentin.net"
        original["Subject"] = "Overlapping content IDs"
        original["Message-ID"] = "<original-overlap@example.com>"
        original["Date"] = "Tue, 12 Aug 2025 10:30:00 +0200"
        original.set_content("Original plain body.")
        original.add_alternative(
            '<img src="cid:image@example.com">'
            '<img src="cid:image@example.com.extra">',
            subtype="html",
        )
        related = original.get_payload()[-1]
        related.add_related(
            b"short-id-image",
            maintype="image",
            subtype="png",
            cid="<image@example.com>",
            disposition="inline",
        )
        related.add_related(
            b"long-id-image",
            maintype="image",
            subtype="png",
            cid="<image@example.com.extra>",
            disposition="inline",
        )
        response = {
            "id": "message-123",
            "threadId": "thread-overlap",
            "raw": base64.urlsafe_b64encode(original.as_bytes()).rstrip(b"=").decode("ascii"),
        }
        response_path = message.bundle / "overlapping-response.json"
        response_path.write_text(json.dumps(response), encoding="utf-8")

        result = subprocess.run(
            [
                "python3",
                str(ROOT / "_extensions" / "mail" / "mime.py"),
                "prepare",
                str(message.bundle),
                str(response_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        parsed = parse_message(message.eml)
        html_content = next(
            part for part in parsed.walk() if part.get_content_type() == "text/html"
        ).get_content()
        expected_payloads = {b"short-id-image", b"long-id-image"}
        quoted_parts = [
            part
            for part in parsed.walk()
            if part.get_payload(decode=True) in expected_payloads
        ]
        self.assertEqual(len(quoted_parts), 2)
        for part in quoted_parts:
            content_id = str(part["Content-ID"]).strip("<>")
            self.assertIn(f'cid:{content_id}"', html_content)


if __name__ == "__main__":
    unittest.main()
