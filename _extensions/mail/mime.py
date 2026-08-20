"""Build deterministic MIME artifacts and prepare Gmail API replies."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import shlex
import sys
import tempfile
from email.headerregistry import Address, HeaderRegistry
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import SMTP, default
from email.utils import formatdate, getaddresses
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, ClassVar

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
FINAL_ARTIFACTS = ("message.eml", "gmail-request.json", "gmail-draft-request.json", "reply.json")
MESSAGE_ID_PATTERN = re.compile(r"<[^<>\s]+>")
CID_REFERENCE_END = r"(?=$|[\s\"'(),<>])"
HEADER_REGISTRY = HeaderRegistry()


class HTMLTextExtractor(HTMLParser):
    """Extract readable plain text from an HTML body without dependencies."""

    BREAK_TAGS: ClassVar[set[str]] = {"br", "div", "li", "p", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BREAK_TAGS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BREAK_TAGS and self.parts and not self.parts[-1].endswith("\n"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts).replace("\r\n", "\n").replace("\r", "\n")
        value = re.sub(r"[ \t]+\n", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip("\n")


def decode_base64url(value: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as error:
        raise ValueError("the Gmail response contains invalid base64url data") from error


def encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def read_manifest(bundle: Path) -> dict[str, Any]:
    try:
        return json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"missing rendered manifest: {bundle / 'manifest.json'}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid rendered manifest: {error}") from error


def parse_mailbox(value: Any, field: str) -> Address:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"manifest field '{field}' must contain a non-empty mailbox")
    if "\r" in value or "\n" in value:
        raise ValueError(f"manifest field '{field}' must not contain newlines")
    try:
        header = HEADER_REGISTRY("To", value)
    except Exception as error:
        raise ValueError(f"invalid mailbox {value!r} in manifest field '{field}'") from error
    addresses = header.addresses
    if header.defects or len(addresses) != 1:
        raise ValueError(f"invalid mailbox {value!r} in manifest field '{field}'")
    address = addresses[0]
    if not address.username or not address.domain:
        raise ValueError(f"invalid mailbox {value!r} in manifest field '{field}'")
    return address


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    required_strings = ("source", "account", "from", "body_text", "body_html")
    for field in required_strings:
        value = manifest.get(field)
        if not isinstance(value, str) or value == "":
            raise ValueError(f"manifest field '{field}' must be a non-empty string")
        if "\r" in value or "\n" in value:
            raise ValueError(f"manifest field '{field}' must not contain newlines")

    from_address = parse_mailbox(manifest["from"], "from")
    from_name = manifest.get("from_name")
    if from_name is not None:
        if not isinstance(from_name, str) or from_name == "" or "\r" in from_name or "\n" in from_name:
            raise ValueError("manifest field 'from_name' must be a non-empty single-line string")
        from_address = Address(
            display_name=from_name,
            username=from_address.username,
            domain=from_address.domain,
        )

    parsed: dict[str, Any] = {"from": from_address}
    for field in ("to", "cc", "bcc"):
        values = manifest.get(field)
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError(f"manifest field '{field}' must be a list of mailboxes")
        if field == "to" and not values and not manifest.get("reply_all", False):
            raise ValueError("manifest field 'to' must contain at least one mailbox")
        parsed[field] = [
            parse_mailbox(value, f"{field}[{index}]")
            for index, value in enumerate(values)
        ]

    for field in ("attachments", "inline_images"):
        if not isinstance(manifest.get(field), list):
            raise TypeError(f"manifest field '{field}' must be a list")
    subject = manifest.get("subject")
    reply_id = manifest.get("reply_to_message_id")
    forward_id = manifest.get("forward_message_id")
    if subject is not None and (not isinstance(subject, str) or "\r" in subject or "\n" in subject):
        raise ValueError("manifest field 'subject' must be a single-line string")
    if reply_id is None and forward_id is None and subject is None:
        raise ValueError("manifest field 'subject' is required for a new message")
    if reply_id is not None and forward_id is not None:
        raise ValueError("reply and forward IDs are mutually exclusive")
    if reply_id is not None and (not isinstance(reply_id, str) or reply_id == "" or "\r" in reply_id or "\n" in reply_id):
        raise ValueError("manifest field 'reply_to_message_id' must be a non-empty single-line string")
    if forward_id is not None and (
        not isinstance(forward_id, str)
        or forward_id == ""
        or "\r" in forward_id
        or "\n" in forward_id
    ):
        raise ValueError(
            "manifest field 'forward_message_id' must be a non-empty single-line string"
        )
    if manifest.get("quote", False) not in (True, False):
        raise ValueError("manifest field 'quote' must be a boolean")
    return parsed


def update_digest(digest: Any, label: str, value: bytes) -> None:
    digest.update(label.encode("utf-8"))
    digest.update(b"\0")
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def local_digest(bundle: Path, manifest: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    update_digest(digest, "mime-builder", Path(__file__).read_bytes())
    manifest_bytes = (bundle / "manifest.json").read_bytes()
    update_digest(digest, "manifest", manifest_bytes)
    for key in ("body_text", "body_html"):
        path = bundle / manifest[key]
        update_digest(digest, key, path.read_bytes())
    source = Path(manifest["source"])
    update_digest(digest, "source", source.read_bytes())
    update_digest(digest, "source-mtime-ns", str(source.stat().st_mtime_ns).encode("ascii"))
    for index, path_value in enumerate(manifest["attachments"]):
        update_digest(digest, f"attachment-{index}", Path(path_value).read_bytes())
    for index, image in enumerate(manifest["inline_images"]):
        update_digest(digest, f"inline-image-{index}", Path(image["source"]).read_bytes())
    return digest.hexdigest()


def stable_leaf_bytes(message: EmailMessage) -> list[bytes]:
    return [part.as_bytes(policy=SMTP) for part in message.walk() if not part.is_multipart()]


def content_digest(message: EmailMessage, thread_id: str | None) -> str:
    digest = hashlib.sha256()
    for name in (
        "From",
        "To",
        "Cc",
        "Bcc",
        "Subject",
        "Date",
        "In-Reply-To",
        "References",
    ):
        update_digest(digest, name, str(message.get(name, "")).encode("utf-8"))
    if thread_id is not None:
        update_digest(digest, "threadId", thread_id.encode("utf-8"))
    for index, leaf in enumerate(stable_leaf_bytes(message)):
        update_digest(digest, f"leaf-{index}", leaf)
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


def normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def html_to_text(value: str) -> str:
    parser = HTMLTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def html_fragment(value: str) -> str:
    match = re.search(r"<body\b[^>]*>(.*)</body\s*>", value, re.IGNORECASE | re.DOTALL)
    return (match.group(1) if match else value).strip()


def plain_to_html(value: str) -> str:
    escaped = html.escape(normalize_text(value).strip("\n"))
    return escaped.replace("\n", "<br>\n")


def body_content(message: EmailMessage, subtype: str) -> str | None:
    part = message.get_body(preferencelist=(subtype,))
    if part is None:
        if message.get_content_maintype() == "text" and message.get_content_subtype() == subtype:
            part = message
        else:
            return None
    try:
        content = part.get_content()
    except (LookupError, UnicodeError) as error:
        raise ValueError(f"cannot decode the original {subtype} body: {error}") from error
    if not isinstance(content, str):
        return None
    return normalize_text(content)


def reply_subject(subject: str | None) -> str:
    original = subject or ""
    if re.match(r"^\s*re\s*:", original, re.IGNORECASE):
        return original
    return f"Re: {original}".rstrip()


def reply_context(response: dict[str, Any]) -> dict[str, Any]:
    if "raw" not in response and isinstance(response.get("result"), dict):
        response = response["result"]
    raw_value = response.get("raw")
    thread_id = response.get("threadId")
    if not isinstance(raw_value, str) or raw_value == "":
        raise ValueError("the Gmail response is missing a raw RFC message")
    if not isinstance(thread_id, str) or thread_id == "":
        raise ValueError("the Gmail response is missing threadId")
    original = BytesParser(policy=default).parsebytes(decode_base64url(raw_value))
    message_id_header = str(original.get("Message-ID", ""))
    match = MESSAGE_ID_PATTERN.search(message_id_header)
    if match is None:
        raise ValueError("the original message is missing a valid RFC Message-ID header")
    message_id = match.group(0)
    reference_ids: list[str] = []
    for value in original.get_all("References", []):
        for reference in MESSAGE_ID_PATTERN.findall(str(value)):
            if reference not in reference_ids:
                reference_ids.append(reference)
    if message_id not in reference_ids:
        reference_ids.append(message_id)
    original_plain = body_content(original, "plain")
    original_html = body_content(original, "html")
    if original_plain is None and original_html is None:
        raise ValueError("the original message has no readable plain-text or HTML body")
    if original_plain is None:
        original_plain = html_to_text(original_html or "")
    quoted_inline_images: list[dict[str, Any]] = []
    if original_html is None:
        original_html = plain_to_html(original_plain)
    else:
        original_html = html_fragment(original_html)
        for part in original.walk():
            content_id_header = part.get("Content-ID")
            if content_id_header is None or part.is_multipart():
                continue
            content_id = str(content_id_header).strip().strip("<>")
            reference_pattern = re.compile(
                rf"cid:{re.escape(content_id)}{CID_REFERENCE_END}",
                re.IGNORECASE,
            )
            if not reference_pattern.search(original_html):
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            suffix = hashlib.sha256(content_id.encode("utf-8") + b"\0" + payload).hexdigest()[:16]
            rewritten_content_id = (
                f"quoted-{len(quoted_inline_images) + 1}-{suffix}@quarto-mail"
            )
            original_html = reference_pattern.sub(
                f"cid:{rewritten_content_id}",
                original_html,
            )
            quoted_inline_images.append({
                "content_id": rewritten_content_id,
                "content_type": part.get_content_type(),
                "filename": part.get_filename(),
                "payload": payload,
            })
    attachments: list[dict[str, Any]] = []

    def collect_attachments(part: EmailMessage, inside_related: bool = False) -> None:
        if part.is_multipart():
            related = inside_related or part.get_content_subtype() == "related"
            for child in part.iter_parts():
                collect_attachments(child, related)
            return
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        if disposition != "attachment" and (
            filename is None or disposition == "inline" or inside_related
        ):
            return
        payload = part.get_payload(decode=True)
        if payload is not None:
            attachments.append({
                "filename": filename,
                "content_type": part.get_content_type(),
                "payload": payload,
            })

    collect_attachments(original)
    return {
        "gmail_message_id": response.get("id"),
        "thread_id": thread_id,
        "message_id": message_id,
        "references": reference_ids,
        "from": str(original.get("From", "")),
        "to": [str(x) for x in original.get_all("To", [])],
        "cc": [str(x) for x in original.get_all("Cc", [])],
        "date": str(original.get("Date", "")),
        "subject": str(original.get("Subject", "")),
        "plain": original_plain.strip("\n"),
        "html": original_html,
        "inline_images": quoted_inline_images,
        "attachments": attachments,
    }


def quote_bodies(plain: str, html_body: str, context: dict[str, Any]) -> tuple[str, str]:
    attribution = f"On {context['date']}, {context['from']} wrote:"
    quoted_plain = "\n".join(
        ">" if line == "" else f"> {line}" for line in context["plain"].split("\n")
    )
    plain = plain.rstrip("\n") + "\n\n" + attribution + "\n" + quoted_plain + "\n"
    attribution_html = html.escape(attribution)
    quoted_html = (
        '<div class="gmail_quote">'
        f'<div dir="ltr" class="gmail_attr">{attribution_html}<br></div>'
        '<blockquote class="gmail_quote" '
        'style="margin:0 0 0 .8ex;border-left:1px #ccc solid;padding-left:1ex">'
        f"{context['html']}</blockquote></div>"
    )
    html_body = html_body.rstrip() + "\n" + quoted_html + "\n"
    return plain, html_body


def forward_subject(subject: str | None) -> str:
    if re.match(r"^\s*fwd?\s*:", subject or "", re.IGNORECASE):
        return subject or ""
    return f"Fwd: {subject or ''}".rstrip()


def forward_bodies(
    plain: str,
    html_body: str,
    context: dict[str, Any],
) -> tuple[str, str]:
    header_lines = [
        "---------- Forwarded message ---------",
        f"From: {context['from']}",
        f"Date: {context['date']}",
        f"Subject: {context['subject']}",
        f"To: {', '.join(context['to'])}",
    ]
    if context["cc"]:
        header_lines.append(f"Cc: {', '.join(context['cc'])}")
    header = "\n".join(header_lines)
    forwarded_plain = plain.rstrip() + "\n\n" + header + "\n\n" + context["plain"] + "\n"
    forwarded_header = html.escape(header).replace("\n", "<br>")
    forwarded_html = (
        html_body.rstrip()
        + f'<br><br><div class="gmail_quote">{forwarded_header}'
        + f'<br><br>{context["html"]}</div>\n'
    )
    return forwarded_plain, forwarded_html


def derive_reply_all(
    mailboxes: dict[str, Any],
    context: dict[str, Any],
) -> None:
    seen = {mailboxes["from"].addr_spec.lower()}
    recipients: list[Address] = []
    original_recipients = [context["from"], *context["to"], *context["cc"]]
    for name, address in getaddresses(original_recipients):
        if address and address.lower() not in seen:
            seen.add(address.lower())
            recipients.append(Address(display_name=name, addr_spec=address))
    if not recipients:
        raise ValueError("reply-all found no recipients")
    mailboxes["to"] = recipients[:1]
    mailboxes["cc"] = recipients[1:]


def build_message(
    bundle: Path,
    manifest: dict[str, Any],
    mailboxes: dict[str, Any],
    context: dict[str, Any] | None,
) -> tuple[bytes, dict[str, str], dict[str, Any] | None]:
    message = EmailMessage(policy=SMTP)
    if manifest.get("reply_all") and context is not None:
        derive_reply_all(mailboxes, context)
    message["From"] = mailboxes["from"]
    message["To"] = mailboxes["to"]
    if mailboxes["cc"]:
        message["Cc"] = mailboxes["cc"]
    if mailboxes["bcc"]:
        message["Bcc"] = mailboxes["bcc"]

    thread_id: str | None = None
    preparation_metadata: dict[str, Any] | None = None
    if manifest.get("reply_to_message_id") is not None:
        if context is None:
            raise ValueError("reply preparation requires a Gmail API response")
        if context.get("gmail_message_id") not in (None, manifest["reply_to_message_id"]):
            raise ValueError("the Gmail response does not match mail.reply-to-message-id")
        thread_id = context["thread_id"]
        message["In-Reply-To"] = context["message_id"]
        message["References"] = " ".join(context["references"])
        subject = (
            manifest["subject"]
            if manifest.get("subject") is not None
            else reply_subject(context["subject"])
        )
        preparation_metadata = {
            "operation": "reply",
            "gmail_message_id": manifest["reply_to_message_id"],
            "thread_id": thread_id,
            "message_id": context["message_id"],
            "references": context["references"],
            "from": context["from"],
            "date": context["date"],
            "subject": context["subject"],
        }
    elif manifest.get("forward_message_id") is not None:
        if context is None:
            raise ValueError("forward preparation requires a Gmail API response")
        if context.get("gmail_message_id") not in (None, manifest["forward_message_id"]):
            raise ValueError("the Gmail response does not match mail.forward-message-id")
        subject = manifest.get("subject") or forward_subject(context["subject"])
        preparation_metadata = {
            "operation": "forward",
            "gmail_message_id": manifest["forward_message_id"],
            "thread_id": None,
            "message_id": context["message_id"],
            "from": context["from"],
            "date": context["date"],
            "subject": context["subject"],
        }
    else:
        subject = manifest["subject"]
    message["Subject"] = subject
    source = Path(manifest["source"])
    message["Date"] = formatdate(source.stat().st_mtime, usegmt=True)

    plain = (bundle / manifest["body_text"]).read_text(encoding="utf-8")
    html_body = (bundle / manifest["body_html"]).read_text(encoding="utf-8")
    if context is not None and manifest.get("forward_message_id") is not None:
        plain, html_body = forward_bodies(plain, html_body, context)
    elif context is not None and manifest["quote"]:
        plain, html_body = quote_bodies(plain, html_body, context)

    message.set_content(plain, charset="utf-8")
    message.add_alternative(html_body, subtype="html", charset="utf-8")
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
    if context is not None and (
        manifest["quote"] or manifest.get("forward_message_id") is not None
    ):
        for image in context["inline_images"]:
            maintype, subtype = image["content_type"].split("/", 1)
            options: dict[str, Any] = {
                "maintype": maintype,
                "subtype": subtype,
                "cid": f"<{image['content_id']}>",
                "disposition": "inline",
            }
            if image["filename"] is not None:
                options["filename"] = image["filename"]
            html_part.add_related(image["payload"], **options)

    if (
        context is not None
        and manifest.get("forward_message_id") is not None
        and manifest.get("include_original_attachments", True)
    ):
        for attachment in context["attachments"]:
            maintype, subtype = attachment["content_type"].split("/", 1)
            message.add_attachment(
                attachment["payload"],
                maintype=maintype,
                subtype=subtype,
                filename=attachment["filename"],
                disposition="attachment",
            )

    for source_value in manifest["attachments"]:
        path = Path(source_value)
        content_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        maintype, subtype = content_type.split("/", 1)
        message.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
            disposition="attachment",
        )

    digest = content_digest(message, thread_id)
    message["Message-ID"] = f"<{digest}@quarto-mail>"
    set_boundaries(message, digest)
    raw = message.as_bytes(policy=SMTP)
    request = {"raw": encode_base64url(raw)}
    if thread_id is not None:
        request["threadId"] = thread_id
    return raw, request, preparation_metadata


def remove_artifacts(bundle: Path) -> None:
    for name in FINAL_ARTIFACTS:
        (bundle / name).unlink(missing_ok=True)


def atomic_write(path: Path, value: bytes, mode: int | None = None) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
        if mode is not None:
            temporary.chmod(mode)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_final_artifacts(
    bundle: Path,
    raw: bytes,
    request: dict[str, str],
    preparation_metadata: dict[str, Any] | None,
    digest: str,
) -> None:
    atomic_write(bundle / "message.eml", raw)
    atomic_write(
        bundle / "gmail-request.json",
        (json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"),
    )
    if read_manifest(bundle).get("delivery") == "draft":
        draft_request = json.dumps(
            {"message": request},
            separators=(",", ":"),
        ) + "\n"
        atomic_write(
            bundle / "gmail-draft-request.json",
            draft_request.encode("utf-8"),
        )
    if preparation_metadata is not None:
        preparation_metadata = {"render_digest": digest, **preparation_metadata}
        atomic_write(
            bundle / "reply.json",
            (json.dumps(preparation_metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )


def prepared_message_is_current(bundle: Path, digest: str) -> bool:
    try:
        manifest = read_manifest(bundle)
        state = json.loads((bundle / "reply.json").read_text(encoding="utf-8"))
        raw = (bundle / "message.eml").read_bytes()
        request = json.loads((bundle / "gmail-request.json").read_text(encoding="utf-8"))
        operation = "reply" if manifest.get("reply_to_message_id") is not None else "forward"
        message_id = manifest.get("reply_to_message_id") or manifest.get("forward_message_id")
        if not (
            state.get("render_digest") == digest
            and state.get("operation") == operation
            and state.get("gmail_message_id") == message_id
            and request.get("threadId") == state.get("thread_id")
            and decode_base64url(request["raw"]) == raw
        ):
            return False
        if manifest.get("delivery") == "draft":
            draft_request = json.loads(
                (bundle / "gmail-draft-request.json").read_text(encoding="utf-8")
            )
            return draft_request.get("message") == request
        return True
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def prepare_script(bundle: Path, manifest: dict[str, Any]) -> bytes:
    params = json.dumps(
        {
            "userId": "me",
            "id": manifest.get("reply_to_message_id") or manifest.get("forward_message_id"),
            "format": "raw",
        },
        separators=(",", ":"),
    )
    script = Path(__file__).resolve()
    lines = [
        "#!/bin/sh",
        "set -eu",
        f"bundle={shlex.quote(str(bundle.resolve()))}",
        'response=$(mktemp "${TMPDIR:-/tmp}/quarto-mail-reply.XXXXXX")',
        "trap 'rm -f \"$response\"' EXIT HUP INT TERM",
        f"gog --readonly --account {shlex.quote(manifest['account'])} api call gmail v1 gmail.users.messages.get \\",
        f"  --params {shlex.quote(params)} \\",
        '  --no-input > "$response"',
        f"python3 {shlex.quote(str(script))} prepare \"$bundle\" \"$response\"",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def render(bundle: Path) -> None:
    manifest = read_manifest(bundle)
    mailboxes = validate_manifest(manifest)
    digest = local_digest(bundle, manifest)
    preparation = bundle / "prepare.sh"
    if (
        manifest.get("reply_to_message_id") is not None
        or manifest.get("forward_message_id") is not None
    ):
        if not prepared_message_is_current(bundle, digest):
            remove_artifacts(bundle)
        atomic_write(preparation, prepare_script(bundle, manifest), mode=0o755)
        return
    preparation.unlink(missing_ok=True)
    remove_artifacts(bundle)
    raw, request, _preparation_metadata = build_message(bundle, manifest, mailboxes, None)
    write_final_artifacts(bundle, raw, request, None, digest)


def prepare(bundle: Path, response_path: Path) -> None:
    manifest = read_manifest(bundle)
    mailboxes = validate_manifest(manifest)
    if (
        manifest.get("reply_to_message_id") is None
        and manifest.get("forward_message_id") is None
    ):
        raise ValueError("preparation is only required for replies and forwards")
    digest = local_digest(bundle, manifest)
    remove_artifacts(bundle)
    try:
        response = json.loads(response_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid Gmail API response: {error}") from error
    context = reply_context(response)
    raw, request, preparation_metadata = build_message(bundle, manifest, mailboxes, context)
    write_final_artifacts(bundle, raw, request, preparation_metadata, digest)


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in {"render", "prepare"}:
        raise SystemExit("usage: mime.py render BUNDLE_DIRECTORY | mime.py prepare BUNDLE_DIRECTORY RESPONSE_JSON")
    action = sys.argv[1]
    bundle = Path(sys.argv[2])
    try:
        if action == "render" and len(sys.argv) == 3:
            render(bundle)
        elif action == "prepare" and len(sys.argv) == 4:
            prepare(bundle, Path(sys.argv[3]))
        else:
            raise ValueError("invalid arguments")
    except Exception as error:
        remove_artifacts(bundle)
        if action == "render":
            (bundle / "prepare.sh").unlink(missing_ok=True)
        raise SystemExit(f"quarto-mail: {error}") from error


if __name__ == "__main__":
    main()
