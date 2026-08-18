#!/usr/bin/env python3
"""Build quarto-mail's deterministic MIME artifact from a rendered bundle."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formataddr, formatdate
from pathlib import Path


CONTENT_TYPES = {
    ".css": "text/css",
    ".csv": "text/csv",
    ".gif": "image/gif",
    ".htm": "text/html",
    ".html": "text/html",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".json": "application/json",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain",
    ".webp": "image/webp",
    ".xml": "application/xml",
    ".zip": "application/zip",
}


def stable_leaf_bytes(message: EmailMessage) -> list[bytes]:
    return [part.as_bytes(policy=SMTP) for part in message.walk() if not part.is_multipart()]


def content_digest(message: EmailMessage) -> str:
    digest = hashlib.sha256()
    for name in ("From", "To", "Cc", "Bcc", "Subject", "Date"):
        digest.update(name.encode("ascii"))
        digest.update(b":")
        digest.update(str(message.get(name, "")).encode("utf-8"))
        digest.update(b"\0")
    for leaf in stable_leaf_bytes(message):
        digest.update(len(leaf).to_bytes(8, "big"))
        digest.update(leaf)
    return digest.hexdigest()


def set_boundaries(message: EmailMessage, seed: str) -> None:
    leaves = stable_leaf_bytes(message)
    counters: dict[str, int] = {}
    for part in message.walk():
        if not part.is_multipart():
            continue
        subtype = part.get_content_subtype()
        counters[subtype] = counters.get(subtype, 0) + 1
        salt = 0
        while True:
            suffix = hashlib.sha256(
                f"{seed}:{subtype}:{counters[subtype]}:{salt}".encode("ascii")
            ).hexdigest()[:16]
            boundary = f"quarto-mail-{subtype}-{counters[subtype]}-{suffix}"
            marker = boundary.encode("ascii")
            if all(marker not in leaf for leaf in leaves):
                part.set_boundary(boundary)
                break
            salt += 1


def build(bundle: Path) -> bytes:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    message = EmailMessage(policy=SMTP)
    message["From"] = formataddr((manifest.get("from_name") or "", manifest["from"]))
    message["To"] = ", ".join(manifest["to"])
    if manifest["cc"]:
        message["Cc"] = ", ".join(manifest["cc"])
    if manifest["bcc"]:
        message["Bcc"] = ", ".join(manifest["bcc"])
    if manifest["subject"] is not None:
        message["Subject"] = manifest["subject"]
    message["Date"] = formatdate(Path(manifest["source"]).stat().st_mtime, usegmt=True)

    plain = (bundle / manifest["body_text"]).read_text(encoding="utf-8")
    html = (bundle / manifest["body_html"]).read_text(encoding="utf-8")
    message.set_content(plain, charset="utf-8")
    message.add_alternative(html, subtype="html", charset="utf-8")
    html_part = message.get_payload()[-1]

    for image in manifest["inline_images"]:
        maintype, subtype = image["content_type"].split("/", 1)
        html_part.add_related(
            Path(image["source"]).read_bytes(),
            maintype=maintype,
            subtype=subtype,
            cid=f"<{image['content_id']}>",
            filename=image["filename"],
            disposition="inline",
        )

    for source in manifest["attachments"]:
        path = Path(source)
        content_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
            disposition="attachment",
        )

    digest = content_digest(message)
    message["Message-ID"] = f"<{digest}@quarto-mail>"
    set_boundaries(message, digest)
    return message.as_bytes(policy=SMTP)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: mime.py BUNDLE_DIRECTORY")
    bundle = Path(sys.argv[1])
    raw = build(bundle)
    (bundle / "message.eml").write_bytes(raw)
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    (bundle / "gmail-request.json").write_text(
        json.dumps({"raw": encoded}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
