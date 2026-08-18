---
title: Self-contained MIME messages
type: feature
authors:
  - mavam
created: 2026-08-18T07:20:59.548909Z
---

Quarto Mail can now bundle plain text, HTML, local inline images, and regular attachments into a deterministic `message.eml` artifact. HTTPS images remain remote references and rendering never downloads them.

Use the experimental raw Gmail format to prepare a reviewable submission command:

```sh
quarto render message.qmd --to mail-gmail --output -
```

The existing `mail-gog` format remains available for messages without local inline images.
