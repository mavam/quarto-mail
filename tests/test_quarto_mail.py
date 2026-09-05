from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def decode_raw(request):
    raw = request["raw"]
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def parse_message(raw):
    return BytesParser(policy=policy.default).parsebytes(raw)


class QuartoMailTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="quarto-mail-test-")
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        shutil.copytree(ROOT / "_extensions", self.project / "_extensions")
        shutil.copy(ROOT / "_metadata.yml", self.project / "_metadata.yml")
        (self.project / "_quarto.yml").write_text("project:\n  type: default\n")
        self.source = self.project / "message.qmd"
        self.bundle = self.project / "message.mail"
        self.script = self.project / "message.send.sh"
        self.log = self.project / "gog.jsonl"
        self.response = self.project / "response.json"
        shutil.copy(FIXTURES / "gmail-message.json", self.response)
        self.env = {
            **os.environ,
            "PATH": f"{FIXTURES / 'bin'}:{os.environ['PATH']}",
            "FAKE_GMAIL_RESPONSE": str(self.response),
            "FAKE_GOG_LOG": str(self.log),
        }

    def write_source(self, fixture="work", transform=None):
        text = (FIXTURES / f"{fixture}.qmd").read_text()
        text = text.replace("attachment~path~.txt", str(FIXTURES / "attachment~path~.txt"))
        text = text.replace("](inline.png)", f"]({FIXTURES / 'inline.png'})")
        if transform:
            text = transform(text)
        self.source.write_text(text)
        os.utime(self.source, (1_700_000_000, 1_700_000_000))

    def render(self, *args, success=True, source=None):
        result = subprocess.run(
            ["quarto", "render", str(source or self.source), *args],
            cwd=self.project, env=self.env, capture_output=True, text=True, check=False,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def render_gog(self, **kwargs):
        return self.render("--to", "mail-gog", "--output", "-", "--quiet", **kwargs)

    def send(self, success=True, script=None):
        result = subprocess.run(
            ["sh", str(script or self.script)], cwd=self.project, env=self.env,
            capture_output=True, text=True, check=False,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def message(self):
        return parse_message((self.bundle / "message.eml").read_bytes())

    def body(self, subtype):
        return self.message().get_body(preferencelist=(subtype,)).get_content().replace("\r\n", "\n")

    def test_new_message_preview_and_frozen_send(self) -> None:
        self.write_source()
        rendered = self.render_gog()
        self.assertEqual(self.calls(), [])  # New-message rendering is offline.
        self.assertTrue(rendered.stdout.startswith("# Project üpdate\n"))
        self.assertNotIn("# Project", rendered.stderr)
        for text in ("- From:", "- To:", "- Cc:", "- Bcc:", "- Account: work@example.com",
                     "attachment~path~.txt", "inline.png", "The update includes:"):
            self.assertIn(text, rendered.stdout)
        message = self.message()
        self.assertEqual(str(message["From"]), "Alex Example <alias@example.com>")
        self.assertEqual(str(message["Bcc"]), "Archive Example <archive@example.com>")
        raw = (self.bundle / "message.eml").read_bytes()
        request = json.loads((self.bundle / "gmail-request.json").read_text())
        self.assertEqual(decode_raw(request), raw)
        self.assertRegex(str(message["Message-ID"]), r"^<[0-9a-f]{64}@quarto-mail>$")
        self.assertEqual(message.get_content_type(), "multipart/mixed")
        parts = list(message.walk())
        attached = next(part for part in parts if part.get_content_disposition() == "attachment")
        self.assertEqual(attached.get_payload(decode=True), (FIXTURES / "attachment~path~.txt").read_bytes())
        inline = next(part for part in parts if part.get_content_disposition() == "inline")
        self.assertEqual(inline.get_payload(decode=True), (FIXTURES / "inline.png").read_bytes())
        self.assertIn("cid:image-1@quarto-mail", self.body("html"))
        self.assertEqual(self.body("plain"), (self.bundle / "body.txt").read_text())

        frozen_script = self.script.read_bytes()
        self.render_gog()
        self.assertEqual(self.script.read_bytes(), frozen_script)
        # The script owns its request, not the current source or intermediate files.
        self.source.write_text("changed after approval")
        shutil.rmtree(self.bundle)
        copied = self.project / "copied.sh"
        copied.write_bytes(frozen_script)
        result = self.send(script=copied)
        self.assertEqual(json.loads(result.stdout)["id"], "result-123")
        call = self.calls()[0]
        self.assertEqual(call["body"], request)
        self.assertIn("gmail.users.messages.send", call["args"])
        self.assertFalse(Path(call["body_path"]).exists())
        self.send(script=copied)
        self.assertEqual(len(self.calls()), 2)  # Each invocation attempts delivery.

    def test_preview_file_and_stdout_modes(self) -> None:
        self.write_source()
        result = self.render("--to", "mail-gog")
        preview_file = self.project / "message.preview.md"
        self.assertEqual(result.stdout, "")
        expected = preview_file.read_text()
        self.assertIn("# Project üpdate", expected)
        result = self.render_gog()
        self.assertEqual(result.stdout, expected)
        self.assertFalse(preview_file.exists())
        self.render("--to", "mail-gog", "--output", "review.md")
        self.assertEqual((self.project / "review.md").read_text(), expected)
        self.assertTrue(self.script.is_file())

    def test_preview_cannot_overwrite_delivery_script(self) -> None:
        self.write_source()
        result = self.render("--to", "mail-gog", "--output", "message.send.sh", success=False)
        self.assertIn("must not overwrite the delivery script", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_nested_source_with_spaces(self) -> None:
        self.write_source()
        nested = self.project / "nested mail"
        nested.mkdir()
        source = nested / "message.qmd"
        self.source.rename(source)
        result = self.render_gog(source=source)
        self.assertIn("# Project üpdate", result.stdout)
        self.assertTrue((nested / "message.send.sh").exists())
        self.send(script=nested / "message.send.sh")

    def test_complete_reply_and_threaded_send(self) -> None:
        self.write_source("reply")
        result = self.render_gog()
        self.assertIn("# Re: Original üpdate", result.stdout)
        self.assertIn("> Original plain body.\n> Second line.", result.stdout)
        self.assertIn("original-inline.png", result.stdout)
        message = self.message()
        self.assertEqual(str(message["In-Reply-To"]), "<original-123@example.com>")
        self.assertEqual(str(message["References"]).strip(),
                         "<root@example.com> <previous@example.com> <original-123@example.com>")
        self.assertIn("gmail_quote", self.body("html"))
        self.assertIn("Original <strong>HTML</strong> body.", self.body("html"))
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertIn("--readonly", calls[0]["args"])
        self.send()
        self.assertEqual(self.calls()[-1]["body"]["threadId"], "thread-456")

    def test_unquoted_reply_and_explicit_subject(self) -> None:
        self.write_source("reply", lambda text: text.replace(
            "  quote: true", "  quote: false\n  subject: Replacement ✓"
        ))
        result = self.render_gog()
        self.assertIn("# Replacement ✓", result.stdout)
        self.assertNotIn("Original plain body", result.stdout)
        self.assertNotIn("gmail_quote", self.body("html"))
        self.assertEqual(str(self.message()["In-Reply-To"]), "<original-123@example.com>")

    def test_forward_includes_attachments_and_can_omit_them(self) -> None:
        original_response = json.loads(self.response.read_text())
        original = parse_message(decode_raw(original_response))
        original.add_attachment(b"forwarded bytes", maintype="application", subtype="pdf", filename="original.pdf")
        original_response["raw"] = base64.urlsafe_b64encode(original.as_bytes()).decode().rstrip("=")
        self.response.write_text(json.dumps(original_response))
        self.write_source("reply", lambda text: text.replace(
            "reply-to-message-id:", "forward-message-id:"
        ))
        result = self.render_gog()
        self.assertIn("# Fwd: Original üpdate", result.stdout)
        self.assertIn("Forwarded message", result.stdout)
        self.assertIn("Original plain body", result.stdout)
        self.assertIn("original.pdf", result.stdout)
        self.assertIsNone(self.message()["In-Reply-To"])
        self.send()
        self.assertNotIn("threadId", self.calls()[-1]["body"])
        text = self.source.read_text().replace("  quote: true", "  include-original-attachments: false")
        self.source.write_text(text)
        result = self.render_gog()
        self.assertNotIn("original.pdf", result.stdout)

    def test_draft_create_and_update(self) -> None:
        for draft_id in (None, "draft-123"):
            with self.subTest(draft_id=draft_id):
                addition = "\n  delivery: draft" + (f"\n  draft-id: {draft_id}" if draft_id else "")
                self.write_source(transform=lambda text, addition=addition: text.replace(
                    "  sender: work", "  sender: work" + addition
                ))
                result = self.render_gog()
                self.assertIn("Update draft draft-123" if draft_id else "Create draft", result.stdout)
                self.send()
                call = self.calls()[-1]
                self.assertIn("gmail.users.drafts.update" if draft_id else "gmail.users.drafts.create", call["args"])
                self.assertEqual(decode_raw(call["body"]["message"]), (self.bundle / "message.eml").read_bytes())
                params = json.loads(call["args"][call["args"].index("--params") + 1])
                self.assertEqual(params.get("id"), draft_id)

    def test_reply_all_replaces_explicit_recipients(self) -> None:
        self.write_source("reply", lambda text: text.replace("  quote: true", "  quote: true\n  reply-all: true"))
        self.render_gog()
        self.assertIn("sender@example.com", str(self.message()["To"]))
        self.assertIn("participant@example.com", str(self.message()["Cc"]))
        self.assertNotIn("user@example.com", str(self.message()["To"]) + str(self.message()["Cc"]))
        self.assertIn("archive@example.com", str(self.message()["Bcc"]))

    def test_all_render_formats_finalize_replies(self) -> None:
        self.write_source("reply")
        self.render("--to", "mail-eml", "--output", "message.eml", "--quiet")
        self.assertEqual((self.project / "message.eml").read_bytes(), (self.bundle / "message.eml").read_bytes())
        plain = self.render("--to", "mail-plain", "--output", "-", "--quiet")
        self.assertIn("Thank you", plain.stdout)
        self.render("--to", "mail-html", "--quiet")
        self.assertTrue((self.project / "message.html").exists())
        self.assertTrue(all("gmail.users.messages.get" in call["args"] for call in self.calls()))

    def test_failed_read_invalidates_old_delivery_script(self) -> None:
        self.write_source("reply")
        self.render_gog()
        self.env["FAKE_GOG_FAIL"] = "1"
        result = self.render_gog(success=False)
        self.assertIn("synthetic Gmail failure", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.script.exists())
        self.assertFalse((self.bundle / "message.eml").exists())

    def test_invalid_response_fails_without_a_preview(self) -> None:
        self.write_source("reply")
        self.response.write_text("{}")
        result = self.render_gog(success=False)
        self.assertIn("missing a raw RFC message", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.script.exists())

    def test_delivery_failure_propagates_and_can_be_invoked_again(self) -> None:
        self.write_source()
        self.render_gog()
        self.env["FAKE_GOG_FAIL"] = "1"
        result = self.send(success=False)
        self.assertEqual(result.returncode, 7)
        self.assertIn("synthetic Gmail failure", result.stderr)
        self.assertFalse(Path(self.calls()[-1]["body_path"]).exists())
        del self.env["FAKE_GOG_FAIL"]
        self.send()
        self.assertEqual(len(self.calls()), 2)

    def test_invalid_metadata_removes_stale_script(self) -> None:
        self.write_source()
        self.render_gog()
        self.source.write_text(self.source.read_text().replace("  subject: Project üpdate\n", ""))
        self.render_gog(success=False)
        self.assertFalse(self.script.exists())
        self.assertFalse((self.bundle / "message.eml").exists())

    def test_invalid_addresses_fail_before_network_reads(self) -> None:
        for address in ("broken", "a@example.com, b@example.com", "Name <a@example.com> trailing"):
            with self.subTest(address=address):
                self.write_source("reply", lambda text, address=address: text.replace(
                    "Original Sender <sender@example.com>", address
                ))
                self.render_gog(success=False)
                self.assertEqual(self.calls(), [])

    def test_display_names_and_account_alias(self) -> None:
        self.write_source(transform=lambda text: text.replace(
            "Customer Example <customer@example.com>", '\'"Doe, Jäne" <customer@example.com>\''
        ))
        metadata = self.project / "_metadata.yml"
        metadata.write_text(metadata.read_text().replace("account: work@example.com", "account: named-work"))
        result = self.render_gog()
        self.assertIn("named-work", result.stdout)
        self.assertEqual(self.message()["To"].addresses[0].display_name, "Doe, Jäne")
        self.send()
        args = self.calls()[0]["args"]
        self.assertEqual(args[args.index("--account") + 1], "named-work")

    def test_sender_display_name_fallback(self) -> None:
        self.write_source()
        metadata = self.project / "_metadata.yml"
        metadata.write_text(metadata.read_text().replace("      name: Alex Example\n", "", 1))
        self.render_gog()
        self.assertEqual(self.message()["From"].addresses[0].display_name, "Alex Example")

    def test_outlook_filenames_are_sanitized(self) -> None:
        response = json.loads(self.response.read_text())
        raw = decode_raw(response).replace(
            b'filename="original-inline.png"', b"filename*=utf-8''Outlook-Logo%0A%0ADesc.png"
        )
        response["raw"] = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        self.response.write_text(json.dumps(response))
        self.write_source("reply")
        result = self.render_gog()
        self.assertIn("Outlook-Logo Desc.png", result.stdout)
        quoted = next(part for part in self.message().walk() if str(part.get("Content-ID", "")).startswith("<quoted-"))
        self.assertEqual(quoted.get_filename(), "Outlook-Logo Desc.png")

    def test_overlapping_cids_and_filename_only_attachments(self) -> None:
        original = EmailMessage(policy=policy.SMTP)
        original["From"] = "Sender <sender@example.com>"
        original["To"] = "Recipient <recipient@example.com>"
        original["Subject"] = "Original attachments"
        original["Message-ID"] = "<original@example.com>"
        original["Date"] = "Tue, 12 Aug 2025 10:30:00 +0200"
        original.set_content("Original plain body.")
        original.add_alternative(
            '<img src="cid:image@example.com"><img src="cid:image@example.com.extra">', subtype="html"
        )
        related = original.get_payload()[-1]
        for cid, payload in (("image@example.com", b"short"), ("image@example.com.extra", b"long")):
            related.add_related(payload, maintype="image", subtype="png", cid=f"<{cid}>", filename="related.png")
            part = related.get_payload()[-1]
            del part["Content-Disposition"]
            part.set_param("name", "related.png", header="Content-Type")
        attachment = EmailMessage(policy=policy.SMTP)
        attachment.set_content(b"attachment bytes", maintype="application", subtype="octet-stream")
        attachment.set_param("name", "without-disposition.bin", header="Content-Type")
        original.make_mixed()
        original.attach(attachment)
        raw = original.as_bytes().replace(
            b'name="without-disposition.bin"', b"name*=utf-8''Outlook-Report%0A%0ADesc.bin"
        )
        self.response.write_text(json.dumps({
            "id": "message-123", "threadId": "thread-456",
            "raw": base64.urlsafe_b64encode(raw).decode().rstrip("="),
        }))
        self.write_source("reply", lambda text: text.replace("reply-to-message-id:", "forward-message-id:"))
        rendered = self.render_gog()
        self.assertIn("Outlook-Report Desc.bin", rendered.stdout)
        parts = [part for part in self.message().walk() if part.get_payload(decode=True) in (b"short", b"long")]
        self.assertEqual(len(parts), 2)
        for part in parts:
            cid = str(part["Content-ID"]).strip("<>")
            self.assertIn(f'cid:{cid}"', self.body("html"))
        self.assertEqual(sum(part.get_payload(decode=True) == b"attachment bytes" for part in self.message().walk()), 1)


if __name__ == "__main__":
    unittest.main()
