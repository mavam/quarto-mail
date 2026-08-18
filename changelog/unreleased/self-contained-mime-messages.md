---
title: Self-contained MIME delivery
type: feature
authors:
  - mavam
prs:
  - 1
created: 2026-08-18T07:20:59.548909Z
---

Quarto Mail now sends every new message and reply as a deterministic, reviewable MIME artifact through Gmail's raw API. Messages preserve plain-text and HTML alternatives, inline image bytes, regular attachments, explicit recipients, Unicode headers, and Gmail reply threading.

Render one send script for every message:

```sh
quarto render message.qmd --to mail-gog --output message.send.sh
```

Rendering remains local-only. Replies include a separate `message.mail/prepare.sh` command that reads the original Gmail message and finalizes `message.eml` without sending it. After reviewing the finalized MIME message, run `message.send.sh` to send it once.
