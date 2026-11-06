from __future__ import annotations

import base64
import html
import re
import sys
import unittest
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_extensions" / "mail"))
import mime


class QuoteTests(unittest.TestCase):
    def context(self, plain="Original body", html="<p>Original body</p>"):
        message = EmailMessage()
        message["From"] = '"Doe, Jane" <jane@example.com>'
        message["To"] = "recipient@example.com"
        message["Cc"] = "Other <other@example.com>"
        message["Message-ID"] = "<original@example.com>"
        message["Date"] = "Tue, 12 Aug 2025 10:30:00 +0200"
        message["Subject"] = "A <subject> & more"
        if plain is not None:
            message.set_content(plain)
        if html is not None:
            message.add_alternative(html, subtype="html")
        return mime.reply_context({
            "raw": base64.urlsafe_b64encode(message.as_bytes()).decode(),
            "threadId": "thread-123",
        })

    def test_blank_plain_falls_back_to_html(self):
        for plain in (None, "", " \t\n", "\u00a0"):
            with self.subTest(plain=plain):
                context = self.context(plain, "<p>Meaningful HTML</p>")
                self.assertEqual(context["plain"], "Meaningful HTML")
                for compose in (mime.quote_bodies, mime.forward_bodies):
                    text, _ = compose("Reply", "<p>Reply</p>", context)
                    self.assertIn("Meaningful HTML", text)
        self.assertEqual(self.context("Keep plain", "<p>Other</p>")["plain"], "Keep plain")
        self.assertEqual(self.context(" \t", None)["plain"], " \t")

    def test_reply_attribution_and_safe_links(self):
        text, html = mime.quote_bodies("Reply", '<div dir="auto">Reply</div>', self.context())
        self.assertIn("On Tue, Aug 12, 2025 at 10:30\u202fAM Doe, Jane <jane@example.com> wrote:", text)
        self.assertIn('<div dir="ltr" class="gmail_attr">', html)
        self.assertIn('&lt;<a href="mailto:jane@example.com">jane@example.com</a>&gt;', html)
        self.assertEqual(mime.quote_addresses("bare@example.com"), "<bare@example.com>")
        escaped = mime.quote_addresses('"<script>&" <safe@example.com>', as_html=True, bold_name=True)
        self.assertIn("<b>&lt;script&gt;&amp;</b>", escaped)
        self.assertNotIn("<script>", escaped)

    def test_mailto_links_encode_mailbox_delimiters(self):
        for address in ("ops#eu@example.com", "ops?bcc=hidden@example.com",
                        "ops%25@example.com", "ops&eu@example.com"):
            with self.subTest(address=address):
                rendered = mime.quote_addresses(address, as_html=True)
                uri = html.unescape(re.search(r'href="([^"]+)"', rendered)[1])
                parsed = urlsplit(uri)
                self.assertEqual(parsed.scheme, "mailto")
                self.assertEqual(parsed.query, "")
                self.assertEqual(parsed.fragment, "")
                self.assertEqual(unquote(parsed.path), address)
                self.assertIn(f">{html.escape(address)}</a>", rendered)

    def test_plain_to_html_preserves_whitespace_only_separators(self):
        for separator in ("", "   ", "\t", " \t "):
            with self.subTest(separator=separator):
                context = self.context(f"One\n{separator}\nTwo", None)
                self.assertEqual(context["html"], '<div dir="auto">One</div>\n'
                                 '<div dir="auto"><br></div>\n<div dir="auto">Two</div>')
                self.assertEqual(context["plain"], f"One\n{separator}\nTwo")

    def test_forward_header_and_spacing(self):
        text, html = mime.forward_bodies("Note", "<p>Note</p>", self.context())
        self.assertIn("Cc: Other <other@example.com>\n\n\nOriginal body", text)
        self.assertIn('<div dir="ltr" class="gmail_attr">', html)
        self.assertIn("<b>Doe, Jane</b>", html)
        self.assertIn("Subject: A &lt;subject&gt; &amp; more", html)
        for address in ("jane@example.com", "recipient@example.com", "other@example.com"):
            self.assertIn(f'href="mailto:{address}"', html)
        self.assertIn("</div><br><br><p>Original body</p>", html)

    def test_date_fallback_and_clock(self):
        self.assertEqual(mime.quote_date("not a date"), "not a date")
        self.assertIn("at 12:05\u202fAM", mime.quote_date("Tue, 12 Aug 2025 00:05:00 -0700"))
        self.assertIn("at 12:05\u202fPM", mime.quote_date("Tue, 12 Aug 2025 12:05:00 +0200"))

    def test_plain_to_html_isolates_each_direction(self):
        self.assertEqual(mime.plain_to_html("English\nשלום\n\n<safe>"),
                         '<div dir="auto">English</div>\n<div dir="auto">שלום</div>\n'
                         '<div dir="auto"><br></div>\n<div dir="auto">&lt;safe&gt;</div>')


if __name__ == "__main__":
    unittest.main()
