---
title: Native email-client body rendering
type: bugfix
authors:
  - mavam
created: 2026-08-17T19:28:03.708221Z
---

HTML message bodies now use the recipient's mail client's native typography, colors, and list presentation. Quarto Mail adds no CSS or inline styles outside explicitly configured rich signatures, and avoids inserting extra blank lines around lists.
