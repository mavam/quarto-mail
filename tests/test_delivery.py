from __future__ import annotations

import json
import mimetypes
import subprocess
import sys
import unittest
from email import policy
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_extensions" / "mail"))
import delivery


class PreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.message = EmailMessage(policy=policy.SMTP)
        self.message["Subject"] = "Project üpdate"
        self.message["From"] = "Alex Example <alex@example.com>"
        self.message["To"] = '"Doe, Jäne" <jane@example.com>, Ben <ben@example.com>'
        self.message.set_content("Hello,\n\nA complete body.\n\nBest,\n    Alex\n")
        self.manifest = {"account": "alex@example.com", "delivery": "send"}

    def preview(self) -> str:
        return delivery.preview(self.message.as_bytes(), self.manifest)

    def test_compact_rows_for_every_recipient_and_attachment(self) -> None:
        self.message["Cc"] = "Grace <grace@example.com>, Hugo <hugo@example.com>"
        self.message["Bcc"] = "Isla <isla@example.com>, archive@example.com"
        self.message.add_attachment(b"x" * 248_000, maintype="application", subtype="pdf", filename="brief.pdf")
        self.message.add_attachment(b"x" * 144, maintype="text", subtype="plain", filename="agenda.txt")
        expected = [
            "```text",
            "≡ Project üpdate",
            "│",
            '→ "Doe, Jäne" <jane@example.com>',
            "→ Ben <ben@example.com>",
            "⇢ Grace <grace@example.com> Ⓒ",
            "⇢ Hugo <hugo@example.com> Ⓒ",
            "◌ Isla <isla@example.com> Ⓑ",
            "◌ archive@example.com Ⓑ",
            "│",
            "⊕ brief.pdf · PDF · 248 KB",
            "⊕ agenda.txt · TXT · 144 B",
            "```",
        ]
        header, body = self.preview().split("\n\n---\n\n", 1)
        self.assertEqual(header.splitlines(), expected)
        self.assertEqual(body, "Hello,\n\nA complete body.\n\nBest,\n    Alex\n")

    def test_empty_and_default_fields_are_omitted(self) -> None:
        preview = self.preview()
        for text in ("◎", "account", "Send", "Delivery", "Attachments", "None", "reply-to", "Ⓒ", "Ⓑ", "⊕"):
            self.assertNotIn(text, preview)

    def test_sender_and_account_are_omitted(self) -> None:
        for account in ("alex@example.com", "other@example.com", "named-work"):
            with self.subTest(account=account):
                self.manifest["account"] = account
                preview = self.preview()
                self.assertNotIn("◎", preview)
                self.assertNotIn("alex@example.com", preview)
                self.assertNotIn(account, preview)

    def test_spine_only_separates_nonempty_groups(self) -> None:
        self.assertEqual(self.preview().count("\n│\n"), 1)
        self.message.add_attachment(b"x", maintype="text", subtype="plain", filename="notes.txt")
        self.assertEqual(self.preview().count("\n│\n"), 2)
        del self.message["To"]
        preview = self.preview()
        self.assertEqual(preview.count("\n│\n"), 1)
        self.assertIn("≡ Project üpdate\n│\n⊕", preview)
        self.assertNotIn("│\n```", preview)

    def test_reply_to_is_visible_only_when_different(self) -> None:
        self.message["Reply-To"] = "Another name <alex@example.com>"
        self.assertNotIn("↪", self.preview())
        self.message.replace_header("Reply-To", "Team <team@example.com>, backup@example.com")
        self.assertIn("↪ Team <team@example.com> · reply-to\n↪ backup@example.com · reply-to\n", self.preview())

    def test_draft_operations_remain_visible(self) -> None:
        self.manifest["delivery"] = "draft"
        self.assertIn("◇ Create draft\n", self.preview())
        self.manifest["draft_id"] = "draft-123"
        self.assertIn("◇ Update draft draft-123\n", self.preview())

    def test_attachment_labels_follow_mime_not_filename(self) -> None:
        cases = [
            ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet", "XLSX"),
            ("application", "vnd.openxmlformats-officedocument.wordprocessingml.document", "DOCX"),
            ("application", "epub+zip", "EPUB"),
            ("audio", "flac", "FLAC"),
            ("font", "woff2", "WOFF2"),
            ("image", "jpeg", "JPEG"),
            ("application", "octet-stream", "Binary"),
            ("application", "x-custom-format", "application/x-custom-format"),
        ]
        for maintype, subtype, label in cases:
            self.message.add_attachment(b"test", maintype=maintype, subtype=subtype, filename="misleading.pdf")
        preview = self.preview()
        for _, _, label in cases:
            self.assertIn(f"⊕ misleading.pdf · {label} · 4 B\n", preview)
        self.assertNotIn(" · PDF", preview)

    def test_attachment_types_ignore_host_mappings(self) -> None:
        host_types = mimetypes.MimeTypes()
        host_types.add_type("application/x-host-only", ".host")
        with patch.object(mimetypes, "_db", host_types):
            self.assertEqual(mimetypes.guess_extension("application/x-host-only"), ".host")
            # Construct the preview database while the global registry is customized.
            with patch.object(delivery, "MIME_TYPES", mimetypes.MimeTypes(filenames=())):
                self.assertEqual(delivery.attachment_type("application/x-host-only"), "application/x-host-only")
                self.assertEqual(delivery.attachment_type("application/pdf"), "PDF")

    def test_inline_and_unnamed_attachments(self) -> None:
        self.message.add_attachment(b"img", maintype="image", subtype="png", filename="logo.png", disposition="inline")
        self.message.add_attachment(b"?", maintype="application", subtype="octet-stream")
        self.assertIn("⊕ logo.png · PNG · 3 B · inline\n", self.preview())
        self.assertIn("⊕ Unnamed attachment · Binary · 1 B\n", self.preview())

    def test_sizes(self) -> None:
        cases = {0: "0 B", 999: "999 B", 1000: "1 KB", 1500: "1.5 KB", 32_000: "32 KB",
                 1_000_000: "1 MB", 1_000_000_000: "1 GB", 1_000_000_000_000: "1 TB"}
        for size, label in cases.items():
            with self.subTest(size=size):
                self.assertEqual(delivery.attachment_size(size), label)

    def test_markdown_preserves_rows_and_literal_metadata(self) -> None:
        self.message.replace_header("Subject", "*Literal* [link](https://example.com) <tag> & ```")
        self.message.add_attachment(b"x", maintype="text", subtype="plain", filename="notes.txt")
        raw = self.message.as_bytes().replace(
            b'filename="notes.txt"', b"filename*=utf-8''notes%0A%60%60%60%0A%23%20injected.txt"
        )
        preview = delivery.preview(raw, self.manifest)
        result = subprocess.run(
            ["quarto", "pandoc", "--from=markdown", "--to=json"],
            input=preview, capture_output=True, text=True, check=True,
        )
        blocks = json.loads(result.stdout)["blocks"]
        self.assertEqual(blocks[0]["t"], "CodeBlock")
        self.assertEqual(blocks[1]["t"], "HorizontalRule")
        lines = blocks[0]["c"][1].splitlines()
        self.assertEqual(lines[0], "≡ *Literal* [link](https://example.com) <tag> & ```")
        self.assertIn('→ "Doe, Jäne" <jane@example.com>', lines)
        self.assertIn("⊕ notes ``` # injected.txt · TXT · 1 B", lines)
        self.assertTrue(all(line and line[0] in "≡◎→⊕│" for line in lines))
        self.assertNotIn("&lt;", preview)

    def test_missing_plain_body_still_fails(self) -> None:
        self.message.set_content("<p>HTML only</p>", subtype="html")
        with self.assertRaisesRegex(ValueError, "no plain-text preview"):
            self.preview()


if __name__ == "__main__":
    unittest.main()
