Quarto Mail now creates self-contained MIME messages for new mail, replies, reply-all, forwards, and Gmail drafts. It also improves sender identities and makes replies to externally generated messages more reliable.

## 🚀 Features

### Forward, reply-all, and draft authoring

Compose forwards, derive reply-all recipients, and save new messages, replies, or forwards as Gmail drafts.

Use `forward-message-id` for forwards, `reply-all: true` for recipient derivation, and `delivery: draft` with an optional `draft-id` for draft creation or updates.

*By @mavam.*

### Self-contained MIME delivery

Quarto Mail now sends every new message and reply as a deterministic, reviewable MIME artifact through Gmail's raw API. Messages preserve plain-text and HTML alternatives, inline image bytes, regular attachments, explicit recipients, Unicode headers, and Gmail reply threading.

Render one send script for every message:

```sh
quarto render message.qmd --to mail-gog --output message.send.sh
```

Rendering remains local-only. Replies include a separate `message.mail/prepare.sh` command that reads the original Gmail message and finalizes `message.eml` without sending it. After reviewing the finalized MIME message, run `message.send.sh` to send it once.

*By @mavam in #1.*

## 🔧 Changes

### Named gog account identities

Sender profiles now accept any single-line `gog` account identity instead of requiring an email-shaped account name. This allows named `gog` identities while message header addresses continue to receive strict local validation.

*By @mavam in #2.*

## 🐞 Bug fixes

### Reliable replies to Outlook messages

Replies now handle malformed or folded attachment filenames from external email clients without failing MIME generation.

*By @mavam in #7.*

### Sender display names from sign-off identities

Messages now use the selected sign-off identity as the sender display name when the sender profile doesn't define `name`:

```yaml
mail-profiles:
  senders:
    personal:
      account: user@example.com
      from: user@example.com
  identities:
    personal:
      name: Alex Example
mail:
  sender: personal
  identity: personal
```

This produces `From: Alex Example <user@example.com>` instead of exposing only the email address. An explicit sender `name` continues to take precedence.

*By @mavam in #4.*
