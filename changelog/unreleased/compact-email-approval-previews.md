---
title: Compact email approval previews
type: change
authors:
  - mavam
prs:
  - 10
created: 2026-09-05T20:27:30.220103Z
---

Email approval previews now use a compact header with one glyph-prefixed row per recipient and attachment, without blank lines between rows:

```text
≡ Project kickoff
◎ Alex Example <alex@example.com>
→ Jane Doe <jane@example.com>
⇢ Grace Park <grace@example.com> · cc
◌ archive@example.com · bcc
⊕ project-brief.pdf · PDF · 248 KB
```

CC and BCC retain explicit suffixes, while attachment types use short labels such as `PDF`, `TXT`, and `XLSX`. The header omits normal sends, empty fields, and sending accounts that match the From address. Different accounts, distinct Reply-To addresses, draft operations, and inline attachments remain visible. Addresses display literally in Markdown, and the outgoing message remains unchanged.
